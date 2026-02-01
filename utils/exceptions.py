"""
Custom exceptions for the financial bot.
All exceptions are designed for financial integrity and clear error handling.
"""
from typing import Optional, Dict, Any


class BotBaseException(Exception):
    """Base exception for all bot errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }


# ============ Network & API Exceptions ============

class NetworkException(BotBaseException):
    """Network-related errors (connection, timeout)."""
    pass


class APITimeoutException(NetworkException):
    """API request timed out."""
    
    def __init__(self, service: str, timeout: float):
        super().__init__(
            f"Request to {service} timed out after {timeout}s",
            {"service": service, "timeout": timeout}
        )


class APIConnectionException(NetworkException):
    """Failed to connect to API."""
    
    def __init__(self, service: str, reason: str):
        super().__init__(
            f"Failed to connect to {service}: {reason}",
            {"service": service, "reason": reason}
        )


class APIResponseException(BotBaseException):
    """Invalid or unexpected API response."""
    
    def __init__(self, service: str, status_code: int, response: Any):
        super().__init__(
            f"{service} returned unexpected response (status: {status_code})",
            {"service": service, "status_code": status_code, "response": str(response)[:500]}
        )


# ============ Transaction Exceptions ============

class TransactionException(BotBaseException):
    """Base exception for transaction errors."""
    
    def __init__(self, message: str, transaction_id: Optional[str] = None, **kwargs):
        details = {"transaction_id": transaction_id, **kwargs}
        super().__init__(message, details)
        self.transaction_id = transaction_id


class InsufficientBalanceException(TransactionException):
    """User has insufficient balance for operation."""
    
    def __init__(self, user_id: int, required: float, available: float, transaction_id: Optional[str] = None):
        super().__init__(
            f"Insufficient balance: required {required}, available {available}",
            transaction_id=transaction_id,
            user_id=user_id,
            required=required,
            available=available
        )


class DuplicateTransactionException(TransactionException):
    """Duplicate transaction detected (idempotency check)."""
    
    def __init__(self, idempotency_key: str, original_transaction_id: str):
        super().__init__(
            f"Duplicate transaction detected for key: {idempotency_key}",
            transaction_id=original_transaction_id,
            idempotency_key=idempotency_key
        )


class TransactionFailedException(TransactionException):
    """Transaction failed during processing."""
    
    def __init__(self, transaction_id: str, stage: str, reason: str):
        super().__init__(
            f"Transaction failed at {stage}: {reason}",
            transaction_id=transaction_id,
            stage=stage,
            reason=reason
        )


class PartialTransactionException(TransactionException):
    """Transaction partially completed - requires manual intervention."""
    
    def __init__(self, transaction_id: str, completed_steps: list, failed_step: str, reason: str):
        super().__init__(
            f"Partial transaction failure at {failed_step}: {reason}",
            transaction_id=transaction_id,
            completed_steps=completed_steps,
            failed_step=failed_step,
            reason=reason
        )


class TransactionStateException(TransactionException):
    """Invalid transaction state transition."""
    
    def __init__(self, transaction_id: str, current_state: str, attempted_state: str):
        super().__init__(
            f"Invalid state transition from {current_state} to {attempted_state}",
            transaction_id=transaction_id,
            current_state=current_state,
            attempted_state=attempted_state
        )


# ============ Payment Exceptions ============

class PaymentException(BotBaseException):
    """Base exception for payment errors."""
    pass


class PaymentVerificationException(PaymentException):
    """Payment verification failed."""
    
    def __init__(self, provider: str, reason: str, payment_ref: Optional[str] = None):
        super().__init__(
            f"Payment verification failed for {provider}: {reason}",
            {"provider": provider, "reason": reason, "payment_ref": payment_ref}
        )


class PaymentProcessingException(PaymentException):
    """Payment processing failed."""
    
    def __init__(self, provider: str, reason: str, payment_ref: Optional[str] = None):
        super().__init__(
            f"Payment processing failed for {provider}: {reason}",
            {"provider": provider, "reason": reason, "payment_ref": payment_ref}
        )


# ============ User Exceptions ============

class UserException(BotBaseException):
    """Base exception for user-related errors."""
    pass


class UserNotFoundException(UserException):
    """User not found in database."""
    
    def __init__(self, identifier: Any):
        super().__init__(
            f"User not found: {identifier}",
            {"identifier": str(identifier)}
        )


class UserAlreadyExistsException(UserException):
    """User already exists."""
    
    def __init__(self, identifier: Any):
        super().__init__(
            f"User already exists: {identifier}",
            {"identifier": str(identifier)}
        )


class UserBlockedException(UserException):
    """User is blocked from using the service."""
    
    def __init__(self, user_id: int, reason: Optional[str] = None):
        super().__init__(
            f"User {user_id} is blocked" + (f": {reason}" if reason else ""),
            {"user_id": user_id, "reason": reason}
        )


# ============ Ichancy API Exceptions ============

class IchancyException(BotBaseException):
    """Base exception for Ichancy API errors."""
    pass


class IchancyPlayerException(IchancyException):
    """Player-related Ichancy errors."""
    pass


class IchancyBalanceException(IchancyException):
    """Balance-related Ichancy errors."""
    pass


# ============ Database Exceptions ============

class DatabaseException(BotBaseException):
    """Database operation failed."""
    pass


class DatabaseConnectionException(DatabaseException):
    """Failed to connect to database."""
    pass


class DatabaseIntegrityException(DatabaseException):
    """Database integrity constraint violated."""
    pass
