"""
Database repository layer with async SQLite operations.
Handles all database CRUD with proper transaction management.
"""
import aiosqlite
from pathlib import Path
from typing import Optional, List, Any
from datetime import datetime
from contextlib import asynccontextmanager

from config import config
from db.models import (
    User, Transaction, Payment, Bonus, BonusUsage, AuditLog,
    TransactionType, TransactionState, PaymentProvider, PaymentState, UserState,
    SCHEMA_SQL
)
from utils.logger import get_logger
from utils.exceptions import (
    DatabaseException, DatabaseConnectionException, DatabaseIntegrityException,
    UserNotFoundException, DuplicateTransactionException
)

logger = get_logger("repository")


class Database:
    """
    Async SQLite database manager.
    Ensures proper connection handling and schema initialization.
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DATABASE_PATH
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        """Initialize database and create schema."""
        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        async with self.connection() as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    @asynccontextmanager
    async def connection(self):
        """Get database connection context manager."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()
    
    @asynccontextmanager
    async def transaction(self):
        """
        Transaction context manager with automatic commit/rollback.
        Usage:
            async with db.transaction() as conn:
                await conn.execute(...)
        """
        async with self.connection() as conn:
            try:
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                logger.error(f"Transaction rolled back: {e}")
                raise


# Global database instance
db = Database()


# ============ User Repository ============

class UserRepository:
    """User CRUD operations."""
    
    @staticmethod
    async def create(user: User) -> User:
        """Create a new user."""
        async with db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, telegram_username, ichancy_username, ichancy_password, ichancy_registered,
                    state, local_balance, total_deposited, total_withdrawn, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user.id, user.telegram_username, user.ichancy_username, user.ichancy_password,
                 int(user.ichancy_registered), user.state.value, user.local_balance,
                 user.total_deposited, user.total_withdrawn, 
                 user.created_at.isoformat(), user.updated_at.isoformat())
            )
        logger.info(f"Created user: {user.id}")
        return user
    
    @staticmethod
    async def get_by_id(user_id: int) -> Optional[User]:
        """Get user by Telegram ID."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return UserRepository._row_to_user(row)
        return None
    
    @staticmethod
    async def get_by_ichancy_username(username: str) -> Optional[User]:
        """Get user by Ichancy username."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE ichancy_username = ?", (username,)
            )
            row = await cursor.fetchone()
            if row:
                return UserRepository._row_to_user(row)
        return None
    
    @staticmethod
    async def update(user: User) -> User:
        """Update user record."""
        user.updated_at = datetime.utcnow()
        async with db.transaction() as conn:
            await conn.execute(
                """
                UPDATE users SET 
                    telegram_username = ?, ichancy_username = ?, ichancy_password = ?, ichancy_registered = ?,
                    state = ?, local_balance = ?, total_deposited = ?, total_withdrawn = ?,
                    updated_at = ?, blocked_reason = ?
                WHERE id = ?
                """,
                (user.telegram_username, user.ichancy_username, user.ichancy_password, int(user.ichancy_registered),
                 user.state.value, user.local_balance, user.total_deposited, user.total_withdrawn,
                 user.updated_at.isoformat(), user.blocked_reason, user.id)
            )
        return user
    
    @staticmethod
    async def update_balance(user_id: int, new_balance: float, 
                            deposit_delta: float = 0, withdraw_delta: float = 0) -> bool:
        """
        Atomically update user balance.
        Returns True if successful.
        """
        async with db.transaction() as conn:
            await conn.execute(
                """
                UPDATE users SET 
                    local_balance = ?,
                    total_deposited = total_deposited + ?,
                    total_withdrawn = total_withdrawn + ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (new_balance, deposit_delta, withdraw_delta, 
                 datetime.utcnow().isoformat(), user_id)
            )
        return True
    
    @staticmethod
    async def get_all(limit: int = 100, offset: int = 0) -> List[User]:
        """Get all users with pagination."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = await cursor.fetchall()
            return [UserRepository._row_to_user(row) for row in rows]
    
    @staticmethod
    def _row_to_user(row: aiosqlite.Row) -> User:
        """Convert database row to User object."""
        return User(
            id=row["id"],
            telegram_username=row["telegram_username"],
            ichancy_username=row["ichancy_username"],
            ichancy_password=row["ichancy_password"],
            ichancy_registered=bool(row["ichancy_registered"]),
            state=UserState(row["state"]),
            local_balance=row["local_balance"],
            total_deposited=row["total_deposited"],
            total_withdrawn=row["total_withdrawn"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            blocked_reason=row["blocked_reason"]
        )


# ============ Transaction Repository ============

class TransactionRepository:
    """Transaction CRUD with idempotency support."""
    
    @staticmethod
    async def create(txn: Transaction) -> Transaction:
        """Create a new transaction with idempotency check."""
        # Check idempotency
        if txn.idempotency_key:
            existing = await TransactionRepository.get_by_idempotency_key(txn.idempotency_key)
            if existing:
                raise DuplicateTransactionException(txn.idempotency_key, existing.id)
        
        async with db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO transactions (id, user_id, type, state, amount, currency,
                    idempotency_key, payment_reference, ichancy_reference, created_at, updated_at,
                    balance_before, balance_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (txn.id, txn.user_id, txn.type.value, txn.state.value, txn.amount,
                 txn.currency, txn.idempotency_key, txn.payment_reference, txn.ichancy_reference,
                 txn.created_at.isoformat(), txn.updated_at.isoformat(),
                 txn.balance_before, txn.balance_after)
            )
        logger.info(f"Created transaction: {txn.id}")
        return txn
    
    @staticmethod
    async def get_by_id(transaction_id: str) -> Optional[Transaction]:
        """Get transaction by ID."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            )
            row = await cursor.fetchone()
            if row:
                return TransactionRepository._row_to_transaction(row)
        return None
    
    @staticmethod
    async def get_by_idempotency_key(key: str) -> Optional[Transaction]:
        """Get transaction by idempotency key."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM transactions WHERE idempotency_key = ?", (key,)
            )
            row = await cursor.fetchone()
            if row:
                return TransactionRepository._row_to_transaction(row)
        return None
    
    @staticmethod
    async def update_state(transaction_id: str, new_state: TransactionState,
                          error_message: str = None) -> bool:
        """
        Update transaction state with validation.
        Returns True if successful.
        """
        txn = await TransactionRepository.get_by_id(transaction_id)
        if not txn:
            return False
        
        if not txn.state.can_transition_to(new_state):
            logger.error(
                f"Invalid state transition: {txn.state.value} -> {new_state.value} for {transaction_id}"
            )
            return False
        
        now = datetime.utcnow()
        async with db.transaction() as conn:
            updates = {
                "state": new_state.value,
                "updated_at": now.isoformat(),
                "error_message": error_message
            }
            
            if new_state == TransactionState.PROCESSING:
                updates["processing_started_at"] = now.isoformat()
            elif new_state in (TransactionState.COMPLETED, TransactionState.FAILED):
                updates["completed_at"] = now.isoformat()
            
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            await conn.execute(
                f"UPDATE transactions SET {set_clause} WHERE id = ?",
                (*updates.values(), transaction_id)
            )
        
        logger.audit_transaction_state_change(transaction_id, txn.state.value, new_state.value)
        return True
    
    @staticmethod
    async def update(txn: Transaction) -> Transaction:
        """Full transaction update."""
        txn.updated_at = datetime.utcnow()
        async with db.transaction() as conn:
            await conn.execute(
                """
                UPDATE transactions SET 
                    state = ?, amount = ?, payment_reference = ?, ichancy_reference = ?,
                    processing_started_at = ?, completed_at = ?, error_message = ?,
                    retry_count = ?, updated_at = ?, balance_before = ?, balance_after = ?
                WHERE id = ?
                """,
                (txn.state.value, txn.amount, txn.payment_reference, txn.ichancy_reference,
                 txn.processing_started_at.isoformat() if txn.processing_started_at else None,
                 txn.completed_at.isoformat() if txn.completed_at else None,
                 txn.error_message, txn.retry_count, txn.updated_at.isoformat(),
                 txn.balance_before, txn.balance_after, txn.id)
            )
        return txn
    
    @staticmethod
    async def get_user_transactions(user_id: int, limit: int = 50) -> List[Transaction]:
        """Get user's transactions."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [TransactionRepository._row_to_transaction(row) for row in rows]
    
    @staticmethod
    async def get_pending_transactions() -> List[Transaction]:
        """Get all pending transactions (for recovery)."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM transactions WHERE state IN ('pending', 'processing') ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            return [TransactionRepository._row_to_transaction(row) for row in rows]
    
    @staticmethod
    def _row_to_transaction(row: aiosqlite.Row) -> Transaction:
        """Convert database row to Transaction object."""
        return Transaction(
            id=row["id"],
            user_id=row["user_id"],
            type=TransactionType(row["type"]),
            state=TransactionState(row["state"]),
            amount=row["amount"],
            currency=row["currency"],
            idempotency_key=row["idempotency_key"],
            payment_reference=row["payment_reference"],
            ichancy_reference=row["ichancy_reference"],
            processing_started_at=datetime.fromisoformat(row["processing_started_at"]) if row["processing_started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            balance_before=row["balance_before"],
            balance_after=row["balance_after"]
        )


# ============ Payment Repository ============

class PaymentRepository:
    """Payment CRUD operations."""
    
    @staticmethod
    async def create(payment: Payment) -> Payment:
        """Create a new payment record."""
        async with db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO payments (id, user_id, transaction_id, provider, state, amount,
                    provider_reference, phone_number, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (payment.id, payment.user_id, payment.transaction_id, payment.provider.value,
                 payment.state.value, payment.amount, payment.provider_reference,
                 payment.phone_number, payment.created_at.isoformat(),
                 payment.expires_at.isoformat() if payment.expires_at else None)
            )
        logger.info(f"Created payment: {payment.id}")
        return payment
    
    @staticmethod
    async def get_by_id(payment_id: str) -> Optional[Payment]:
        """Get payment by ID."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM payments WHERE id = ?", (payment_id,)
            )
            row = await cursor.fetchone()
            if row:
                return PaymentRepository._row_to_payment(row)
        return None
    
    @staticmethod
    async def get_by_reference(provider: PaymentProvider, reference: str) -> Optional[Payment]:
        """Get payment by provider reference."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM payments WHERE provider = ? AND provider_reference = ?",
                (provider.value, reference)
            )
            row = await cursor.fetchone()
            if row:
                return PaymentRepository._row_to_payment(row)
        return None
    
    @staticmethod
    async def update_state(payment_id: str, new_state: PaymentState) -> bool:
        """Update payment state."""
        now = datetime.utcnow()
        async with db.transaction() as conn:
            updates = {"state": new_state.value}
            if new_state == PaymentState.VERIFIED:
                updates["verified_at"] = now.isoformat()
            
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            await conn.execute(
                f"UPDATE payments SET {set_clause} WHERE id = ?",
                (*updates.values(), payment_id)
            )
        return True
    
    @staticmethod
    async def increment_verification_attempts(payment_id: str) -> int:
        """Increment verification attempts counter."""
        async with db.transaction() as conn:
            await conn.execute(
                "UPDATE payments SET verification_attempts = verification_attempts + 1 WHERE id = ?",
                (payment_id,)
            )
            cursor = await conn.execute(
                "SELECT verification_attempts FROM payments WHERE id = ?", (payment_id,)
            )
            row = await cursor.fetchone()
            return row["verification_attempts"] if row else 0
    
    @staticmethod
    def _row_to_payment(row: aiosqlite.Row) -> Payment:
        """Convert database row to Payment object."""
        return Payment(
            id=row["id"],
            user_id=row["user_id"],
            transaction_id=row["transaction_id"],
            provider=PaymentProvider(row["provider"]),
            state=PaymentState(row["state"]),
            amount=row["amount"],
            provider_reference=row["provider_reference"],
            phone_number=row["phone_number"],
            verified_at=datetime.fromisoformat(row["verified_at"]) if row["verified_at"] else None,
            verification_attempts=row["verification_attempts"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
        )


# ============ Bonus Repository ============

class BonusRepository:
    """Bonus CRUD operations."""
    
    @staticmethod
    async def create(bonus: Bonus) -> Bonus:
        """Create a new bonus."""
        async with db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO bonuses (id, code, description, bonus_type, value, min_deposit,
                    max_uses, uses_count, is_active, valid_from, valid_until, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (bonus.id, bonus.code, bonus.description, bonus.bonus_type, bonus.value,
                 bonus.min_deposit, bonus.max_uses, bonus.uses_count, int(bonus.is_active),
                 bonus.valid_from.isoformat(), 
                 bonus.valid_until.isoformat() if bonus.valid_until else None,
                 bonus.created_at.isoformat())
            )
        return bonus
    
    @staticmethod
    async def get_by_code(code: str) -> Optional[Bonus]:
        """Get bonus by code."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM bonuses WHERE code = ? AND is_active = 1", (code.upper(),)
            )
            row = await cursor.fetchone()
            if row:
                return BonusRepository._row_to_bonus(row)
        return None
    
    @staticmethod
    async def check_user_usage(bonus_id: str, user_id: int) -> bool:
        """Check if user has already used this bonus."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM bonus_usage WHERE bonus_id = ? AND user_id = ?",
                (bonus_id, user_id)
            )
            return await cursor.fetchone() is not None
    
    @staticmethod
    async def record_usage(usage: BonusUsage) -> BonusUsage:
        """Record bonus usage."""
        async with db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO bonus_usage (id, bonus_id, user_id, transaction_id, amount_awarded, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (usage.id, usage.bonus_id, usage.user_id, usage.transaction_id,
                 usage.amount_awarded, usage.created_at.isoformat())
            )
            await conn.execute(
                "UPDATE bonuses SET uses_count = uses_count + 1 WHERE id = ?",
                (usage.bonus_id,)
            )
        return usage
    
    @staticmethod
    def _row_to_bonus(row: aiosqlite.Row) -> Bonus:
        """Convert database row to Bonus object."""
        return Bonus(
            id=row["id"],
            code=row["code"],
            description=row["description"],
            bonus_type=row["bonus_type"],
            value=row["value"],
            min_deposit=row["min_deposit"],
            max_uses=row["max_uses"],
            uses_count=row["uses_count"],
            is_active=bool(row["is_active"]),
            valid_from=datetime.fromisoformat(row["valid_from"]),
            valid_until=datetime.fromisoformat(row["valid_until"]) if row["valid_until"] else None,
            created_at=datetime.fromisoformat(row["created_at"])
        )


# ============ Audit Repository ============

class AuditRepository:
    """Audit log operations."""
    
    @staticmethod
    async def log(entry: AuditLog) -> AuditLog:
        """Create audit log entry."""
        async with db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (id, timestamp, event_type, user_id, admin_id,
                    entity_type, entity_id, action, old_value, new_value, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entry.id, entry.timestamp.isoformat(), entry.event_type, entry.user_id,
                 entry.admin_id, entry.entity_type, entry.entity_id, entry.action,
                 entry.old_value, entry.new_value, entry.ip_address, entry.user_agent)
            )
        return entry
    
    @staticmethod
    async def get_user_logs(user_id: int, limit: int = 100) -> List[AuditLog]:
        """Get audit logs for a user."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM audit_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [AuditRepository._row_to_log(row) for row in rows]
    
    @staticmethod
    def _row_to_log(row: aiosqlite.Row) -> AuditLog:
        """Convert row to AuditLog."""
        return AuditLog(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            event_type=row["event_type"],
            user_id=row["user_id"],
            admin_id=row["admin_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            action=row["action"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            ip_address=row["ip_address"],
            user_agent=row["user_agent"]
        )
