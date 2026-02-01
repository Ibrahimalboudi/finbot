"""
Bonus service for managing promotions and bonus codes.
"""
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from db import (
    db, Bonus, BonusUsage, Transaction,
    TransactionType, TransactionState,
    BonusRepository, TransactionRepository, UserRepository
)
from utils.logger import get_logger
from utils.exceptions import UserNotFoundException

logger = get_logger("bonus_service")


@dataclass
class BonusValidationResult:
    """Result of bonus code validation."""
    valid: bool
    bonus: Optional[Bonus] = None
    error: Optional[str] = None
    calculated_amount: float = 0.0


@dataclass
class BonusApplicationResult:
    """Result of applying a bonus."""
    success: bool
    bonus_amount: float = 0.0
    message: str = ""
    transaction_id: Optional[str] = None
    error: Optional[str] = None


class BonusService:
    """
    Bonus management service.
    
    Handles:
    - Bonus code validation
    - Bonus application to deposits
    - Usage tracking (one-time per user)
    """
    
    async def validate_bonus_code(
        self,
        code: str,
        user_id: int,
        deposit_amount: float
    ) -> BonusValidationResult:
        """
        Validate a bonus code for a user and deposit amount.
        
        Checks:
        1. Code exists and is active
        2. Code is within validity period
        3. User hasn't already used this code
        4. Deposit meets minimum requirement
        5. Code hasn't exceeded max uses
        
        Args:
            code: Bonus code to validate
            user_id: User attempting to use code
            deposit_amount: Amount being deposited
            
        Returns:
            BonusValidationResult with validation status
        """
        code = code.upper().strip()
        
        # Get bonus
        bonus = await BonusRepository.get_by_code(code)
        if not bonus:
            return BonusValidationResult(
                valid=False,
                error="Invalid bonus code"
            )
        
        # Check active
        if not bonus.is_active:
            return BonusValidationResult(
                valid=False,
                error="This bonus code is no longer active"
            )
        
        # Check validity period
        now = datetime.utcnow()
        if now < bonus.valid_from:
            return BonusValidationResult(
                valid=False,
                error="This bonus code is not yet active"
            )
        if bonus.valid_until and now > bonus.valid_until:
            return BonusValidationResult(
                valid=False,
                error="This bonus code has expired"
            )
        
        # Check max uses
        if bonus.max_uses and bonus.uses_count >= bonus.max_uses:
            return BonusValidationResult(
                valid=False,
                error="This bonus code has reached its maximum uses"
            )
        
        # Check user usage
        already_used = await BonusRepository.check_user_usage(bonus.id, user_id)
        if already_used:
            return BonusValidationResult(
                valid=False,
                error="You have already used this bonus code"
            )
        
        # Check minimum deposit
        if deposit_amount < bonus.min_deposit:
            return BonusValidationResult(
                valid=False,
                error=f"Minimum deposit of {bonus.min_deposit} required for this bonus"
            )
        
        # Calculate bonus amount
        if bonus.bonus_type == "fixed":
            calculated_amount = bonus.value
        elif bonus.bonus_type == "percentage":
            calculated_amount = deposit_amount * (bonus.value / 100)
        else:
            calculated_amount = bonus.value
        
        return BonusValidationResult(
            valid=True,
            bonus=bonus,
            calculated_amount=calculated_amount
        )
    
    async def apply_bonus(
        self,
        code: str,
        user_id: int,
        deposit_transaction_id: str
    ) -> BonusApplicationResult:
        """
        Apply a bonus to a completed deposit.
        
        Args:
            code: Bonus code
            user_id: User ID
            deposit_transaction_id: ID of the deposit transaction
            
        Returns:
            BonusApplicationResult with outcome
        """
        # Get deposit transaction
        deposit_txn = await TransactionRepository.get_by_id(deposit_transaction_id)
        if not deposit_txn:
            return BonusApplicationResult(
                success=False,
                error="Deposit transaction not found"
            )
        
        if deposit_txn.state != TransactionState.COMPLETED:
            return BonusApplicationResult(
                success=False,
                error="Deposit must be completed before applying bonus"
            )
        
        # Validate bonus
        validation = await self.validate_bonus_code(code, user_id, deposit_txn.amount)
        if not validation.valid:
            return BonusApplicationResult(
                success=False,
                error=validation.error
            )
        
        bonus = validation.bonus
        bonus_amount = validation.calculated_amount
        
        # Get user
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise UserNotFoundException(user_id)
        
        try:
            # Create bonus transaction
            bonus_txn = Transaction(
                user_id=user_id,
                type=TransactionType.BONUS,
                state=TransactionState.COMPLETED,
                amount=bonus_amount,
                idempotency_key=f"bonus_{bonus.id}_{user_id}",
                balance_before=user.local_balance,
                balance_after=user.local_balance + bonus_amount,
                completed_at=datetime.utcnow()
            )
            bonus_txn = await TransactionRepository.create(bonus_txn)
            
            # Update user balance
            new_balance = user.local_balance + bonus_amount
            await UserRepository.update_balance(
                user_id,
                new_balance,
                deposit_delta=bonus_amount
            )
            
            # Record bonus usage
            usage = BonusUsage(
                bonus_id=bonus.id,
                user_id=user_id,
                transaction_id=bonus_txn.id,
                amount_awarded=bonus_amount
            )
            await BonusRepository.record_usage(usage)
            
            logger.info(
                f"Bonus applied: {code} -> user {user_id}, amount: {bonus_amount}",
                bonus_id=bonus.id,
                transaction_id=bonus_txn.id
            )
            
            return BonusApplicationResult(
                success=True,
                bonus_amount=bonus_amount,
                message=f"Bonus of {bonus_amount} applied successfully!",
                transaction_id=bonus_txn.id
            )
            
        except Exception as e:
            logger.error(f"Failed to apply bonus: {e}", exc_info=True)
            return BonusApplicationResult(
                success=False,
                error=str(e)
            )
    
    async def create_bonus(
        self,
        code: str,
        description: str,
        bonus_type: str,
        value: float,
        min_deposit: float = 0.0,
        max_uses: Optional[int] = None,
        valid_until: Optional[datetime] = None
    ) -> Bonus:
        """
        Create a new bonus code.
        
        Args:
            code: Unique bonus code
            description: Human-readable description
            bonus_type: "fixed" or "percentage"
            value: Bonus value (amount or percentage)
            min_deposit: Minimum deposit required
            max_uses: Maximum total uses (None = unlimited)
            valid_until: Expiration date (None = no expiry)
            
        Returns:
            Created Bonus object
        """
        bonus = Bonus(
            code=code.upper(),
            description=description,
            bonus_type=bonus_type,
            value=value,
            min_deposit=min_deposit,
            max_uses=max_uses,
            valid_until=valid_until
        )
        
        bonus = await BonusRepository.create(bonus)
        logger.info(f"Created bonus: {code}", bonus_id=bonus.id)
        
        return bonus
    
    async def get_active_bonuses(self) -> List[Bonus]:
        """Get all active bonus codes."""
        async with db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM bonuses 
                WHERE is_active = 1 
                AND valid_from <= datetime('now')
                AND (valid_until IS NULL OR valid_until > datetime('now'))
                ORDER BY created_at DESC
                """
            )
            rows = await cursor.fetchall()
            return [BonusRepository._row_to_bonus(row) for row in rows]
    
    async def deactivate_bonus(self, code: str) -> bool:
        """Deactivate a bonus code."""
        async with db.transaction() as conn:
            await conn.execute(
                "UPDATE bonuses SET is_active = 0 WHERE code = ?",
                (code.upper(),)
            )
        logger.info(f"Deactivated bonus: {code}")
        return True


# Global service instance
bonus_service = BonusService()
