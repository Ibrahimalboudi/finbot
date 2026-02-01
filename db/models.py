"""
Database models and schema definitions.
All financial tables include audit fields and integrity constraints.
"""
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


# ============ Enums ============

class TransactionType(Enum):
    """Transaction types."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BONUS = "bonus"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class TransactionState(Enum):
    """
    Transaction state machine.
    
    State transitions:
    PENDING -> PROCESSING -> COMPLETED
                         -> FAILED
                         -> PARTIALLY_FAILED (requires manual intervention)
    PENDING -> CANCELLED
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_FAILED = "partially_failed"
    CANCELLED = "cancelled"
    REVERSED = "reversed"
    
    @classmethod
    def valid_transitions(cls) -> dict:
        """Define valid state transitions."""
        return {
            cls.PENDING: [cls.PROCESSING, cls.CANCELLED],
            cls.PROCESSING: [cls.COMPLETED, cls.FAILED, cls.PARTIALLY_FAILED],
            cls.COMPLETED: [cls.REVERSED],
            cls.FAILED: [cls.PENDING],  # Allow retry
            cls.PARTIALLY_FAILED: [],  # Requires manual intervention
            cls.CANCELLED: [],
            cls.REVERSED: [],
        }
    
    def can_transition_to(self, new_state: 'TransactionState') -> bool:
        """Check if transition to new state is valid."""
        valid = self.valid_transitions().get(self, [])
        return new_state in valid


class PaymentProvider(Enum):
    """Payment providers."""
    SYRIATEL_CASH = "syriatel_cash"
    SHAM_CASH = "sham_cash"
    MANUAL = "manual"


class PaymentState(Enum):
    """Payment verification states."""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"


class UserState(Enum):
    """User account states."""
    ACTIVE = "active"
    BLOCKED = "blocked"
    PENDING_VERIFICATION = "pending_verification"


# ============ Data Classes ============

@dataclass
class User:
    """User model."""
    id: int  # Telegram user ID
    telegram_username: Optional[str]
    ichancy_username: Optional[str] = None
    ichancy_password: Optional[str] = None
    ichancy_registered: bool = False
    state: UserState = UserState.ACTIVE
    local_balance: float = 0.0  # Local wallet balance
    total_deposited: float = 0.0
    total_withdrawn: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    blocked_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "telegram_username": self.telegram_username,
            "ichancy_username": self.ichancy_username,
            "ichancy_registered": self.ichancy_registered,
            "state": self.state.value,
            "local_balance": self.local_balance,
            "total_deposited": self.total_deposited,
            "total_withdrawn": self.total_withdrawn,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "blocked_reason": self.blocked_reason
        }


@dataclass
class Transaction:
    """
    Financial transaction model.
    Implements idempotency via idempotency_key.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int = 0
    type: TransactionType = TransactionType.DEPOSIT
    state: TransactionState = TransactionState.PENDING
    amount: float = 0.0
    currency: str = "SYP"
    
    # Idempotency
    idempotency_key: Optional[str] = None
    
    # External references
    payment_reference: Optional[str] = None
    ichancy_reference: Optional[str] = None
    
    # State tracking
    processing_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Error tracking
    error_message: Optional[str] = None
    retry_count: int = 0
    
    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Balances at time of transaction
    balance_before: Optional[float] = None
    balance_after: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type.value,
            "state": self.state.value,
            "amount": self.amount,
            "currency": self.currency,
            "idempotency_key": self.idempotency_key,
            "payment_reference": self.payment_reference,
            "ichancy_reference": self.ichancy_reference,
            "processing_started_at": self.processing_started_at.isoformat() if self.processing_started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "balance_before": self.balance_before,
            "balance_after": self.balance_after
        }


@dataclass
class Payment:
    """Payment record for local payment systems."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int = 0
    transaction_id: Optional[str] = None
    provider: PaymentProvider = PaymentProvider.SYRIATEL_CASH
    state: PaymentState = PaymentState.PENDING
    amount: float = 0.0
    
    # Provider-specific data
    provider_reference: Optional[str] = None  # e.g., transfer code
    phone_number: Optional[str] = None
    
    # Verification
    verified_at: Optional[datetime] = None
    verification_attempts: int = 0
    
    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "transaction_id": self.transaction_id,
            "provider": self.provider.value,
            "state": self.state.value,
            "amount": self.amount,
            "provider_reference": self.provider_reference,
            "phone_number": self.phone_number,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verification_attempts": self.verification_attempts,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }


@dataclass
class Bonus:
    """Bonus/promotion record."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    code: str = ""
    description: str = ""
    bonus_type: str = "fixed"  # fixed, percentage
    value: float = 0.0
    min_deposit: float = 0.0
    max_uses: Optional[int] = None
    uses_count: int = 0
    is_active: bool = True
    valid_from: datetime = field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "description": self.description,
            "bonus_type": self.bonus_type,
            "value": self.value,
            "min_deposit": self.min_deposit,
            "max_uses": self.max_uses,
            "uses_count": self.uses_count,
            "is_active": self.is_active,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "created_at": self.created_at.isoformat()
        }


@dataclass  
class BonusUsage:
    """Track bonus usage per user."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bonus_id: str = ""
    user_id: int = 0
    transaction_id: Optional[str] = None
    amount_awarded: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AuditLog:
    """Audit log entry for compliance."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: str = ""
    user_id: Optional[int] = None
    admin_id: Optional[int] = None
    entity_type: Optional[str] = None  # user, transaction, payment
    entity_id: Optional[str] = None
    action: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# ============ SQL Schema ============

SCHEMA_SQL = """
-- Users table
    CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,  -- Telegram user ID
    telegram_username TEXT,
    ichancy_username TEXT UNIQUE,
    ichancy_password TEXT,
    ichancy_registered INTEGER DEFAULT 0,
    state TEXT DEFAULT 'active',
    local_balance REAL DEFAULT 0.0,
    total_deposited REAL DEFAULT 0.0,
    total_withdrawn REAL DEFAULT 0.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    blocked_reason TEXT
);

-- Transactions table with idempotency
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    state TEXT DEFAULT 'pending',
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'SYP',
    idempotency_key TEXT UNIQUE,
    payment_reference TEXT,
    ichancy_reference TEXT,
    processing_started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    balance_before REAL,
    balance_after REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Payments table
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    transaction_id TEXT,
    provider TEXT NOT NULL,
    state TEXT DEFAULT 'pending',
    amount REAL NOT NULL,
    provider_reference TEXT,
    phone_number TEXT,
    verified_at TEXT,
    verification_attempts INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

-- Bonuses table
CREATE TABLE IF NOT EXISTS bonuses (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    description TEXT,
    bonus_type TEXT DEFAULT 'fixed',
    value REAL NOT NULL,
    min_deposit REAL DEFAULT 0.0,
    max_uses INTEGER,
    uses_count INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    valid_from TEXT DEFAULT CURRENT_TIMESTAMP,
    valid_until TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Bonus usage tracking
CREATE TABLE IF NOT EXISTS bonus_usage (
    id TEXT PRIMARY KEY,
    bonus_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    transaction_id TEXT,
    amount_awarded REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bonus_id) REFERENCES bonuses(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    UNIQUE(bonus_id, user_id)  -- One use per user
);

-- Audit log table
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    admin_id INTEGER,
    entity_type TEXT,
    entity_id TEXT,
    action TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    ip_address TEXT,
    user_agent TEXT
);

-- Admin users table
CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_state ON transactions(state);
CREATE INDEX IF NOT EXISTS idx_transactions_idempotency ON transactions(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_state ON payments(state);
CREATE INDEX IF NOT EXISTS idx_payments_provider_ref ON payments(provider_reference);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
"""
