"""
Structured logging for financial operations.
All financial transactions are logged with full audit trail.
"""
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path
import json

from config import config

# --- FORCE UTF-8 OUTPUT (Windows fix) ---
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


class FinancialLogger:
    """
    Specialized logger for financial operations.
    Ensures complete audit trail for all money-related operations.
    """
    
    def __init__(self, name: str):
        self.name = name
        self._setup_loggers()
    
    def _setup_loggers(self):
        """Setup separate loggers for different concerns."""
        # Ensure log directory exists
        log_dir = config.BASE_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Main application logger
        self.logger = logging.getLogger(f"bot.{self.name}")
        self.logger.setLevel(logging.DEBUG)
        
        # Financial audit logger (separate file, never loses data)
        self.audit_logger = logging.getLogger(f"audit.{self.name}")
        self.audit_logger.setLevel(logging.INFO)
        
        # Console handler
        if not self.logger.handlers:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # File handler for main logs
        if not any(isinstance(h, logging.FileHandler) for h in self.logger.handlers):
            file_handler = logging.FileHandler(
                log_dir / "bot.log",
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
        
        # Audit log handler (append-only, JSON format)
        if not self.audit_logger.handlers:
            audit_handler = logging.FileHandler(
                log_dir / "audit.log",
                encoding="utf-8"
            )
            audit_handler.setLevel(logging.INFO)
            audit_handler.setFormatter(logging.Formatter('%(message)s'))
            self.audit_logger.addHandler(audit_handler)
    
    def _format_audit_entry(self, event: str, data: Dict[str, Any]) -> str:
        """Format audit log entry as JSON."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "logger": self.name,
            "event": event,
            **data
        }
        return json.dumps(entry, default=str, ensure_ascii=False)
    
    # ============ Standard Logging ============
    
    def debug(self, message: str, **kwargs):
        """Debug level logging."""
        self.logger.debug(f"{message} | {kwargs}" if kwargs else message)
    
    def info(self, message: str, **kwargs):
        """Info level logging."""
        self.logger.info(f"{message} | {kwargs}" if kwargs else message)
    
    def warning(self, message: str, **kwargs):
        """Warning level logging."""
        self.logger.warning(f"{message} | {kwargs}" if kwargs else message)
    
    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Error level logging."""
        self.logger.error(f"{message} | {kwargs}" if kwargs else message, exc_info=exc_info)
    
    def critical(self, message: str, exc_info: bool = True, **kwargs):
        """Critical level logging."""
        self.logger.critical(f"{message} | {kwargs}" if kwargs else message, exc_info=exc_info)
    
    # ============ Financial Audit Logging ============
    
    def audit_transaction_start(
        self,
        transaction_id: str,
        transaction_type: str,
        user_id: int,
        amount: float,
        **extra
    ):
        """Log transaction initiation."""
        self.audit_logger.info(self._format_audit_entry(
            "TRANSACTION_START",
            {
                "transaction_id": transaction_id,
                "type": transaction_type,
                "user_id": user_id,
                "amount": amount,
                **extra
            }
        ))
        self.info(
            f"Transaction started: {transaction_id}",
            type=transaction_type,
            user_id=user_id,
            amount=amount
        )
    
    def audit_transaction_state_change(
        self,
        transaction_id: str,
        from_state: str,
        to_state: str,
        reason: Optional[str] = None
    ):
        """Log transaction state change."""
        self.audit_logger.info(self._format_audit_entry(
            "TRANSACTION_STATE_CHANGE",
            {
                "transaction_id": transaction_id,
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason
            }
        ))
        self.info(
            f"Transaction {transaction_id}: {from_state} -> {to_state}",
            reason=reason
        )
    
    def audit_transaction_complete(
        self,
        transaction_id: str,
        success: bool,
        final_state: str,
        **extra
    ):
        """Log transaction completion."""
        self.audit_logger.info(self._format_audit_entry(
            "TRANSACTION_COMPLETE",
            {
                "transaction_id": transaction_id,
                "success": success,
                "final_state": final_state,
                **extra
            }
        ))
        level = self.info if success else self.error
        level(
            f"Transaction completed: {transaction_id}",
            success=success,
            final_state=final_state
        )
    
    def audit_payment_received(
        self,
        user_id: int,
        provider: str,
        amount: float,
        reference: str,
        **extra
    ):
        """Log payment receipt."""
        self.audit_logger.info(self._format_audit_entry(
            "PAYMENT_RECEIVED",
            {
                "user_id": user_id,
                "provider": provider,
                "amount": amount,
                "reference": reference,
                **extra
            }
        ))
        self.info(
            f"Payment received from user {user_id}",
            provider=provider,
            amount=amount,
            reference=reference
        )
    
    def audit_api_call(
        self,
        service: str,
        action: str,
        success: bool,
        duration_ms: float,
        **extra
    ):
        """Log external API call."""
        self.audit_logger.info(self._format_audit_entry(
            "API_CALL",
            {
                "service": service,
                "action": action,
                "success": success,
                "duration_ms": duration_ms,
                **extra
            }
        ))
    
    def audit_balance_change(
        self,
        user_id: int,
        change_type: str,
        amount: float,
        balance_before: float,
        balance_after: float,
        transaction_id: Optional[str] = None
    ):
        """Log balance change."""
        self.audit_logger.info(self._format_audit_entry(
            "BALANCE_CHANGE",
            {
                "user_id": user_id,
                "change_type": change_type,
                "amount": amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "transaction_id": transaction_id
            }
        ))
    
    def audit_security_event(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        **extra
    ):
        """Log security-related events."""
        self.audit_logger.info(self._format_audit_entry(
            f"SECURITY_{event_type}",
            {
                "user_id": user_id,
                "ip_address": ip_address,
                **extra
            }
        ))
        self.warning(f"Security event: {event_type}", user_id=user_id)


def get_logger(name: str) -> FinancialLogger:
    """Get a logger instance for a module."""
    return FinancialLogger(name)
