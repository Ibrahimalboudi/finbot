"""
Retry utilities with exponential backoff and circuit breaker pattern.
Critical for financial operations resilience.
"""
import asyncio
import functools
import time
from typing import Callable, Optional, Type, Tuple, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config import config
from utils.logger import get_logger
from utils.exceptions import NetworkException, APITimeoutException

logger = get_logger("retry")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.
    Opens after threshold failures, allows test requests after timeout.
    """
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: Optional[datetime] = field(default=None, init=False)
    _half_open_calls: int = field(default=0, init=False)
    
    @property
    def state(self) -> CircuitState:
        """Get current state, transitioning if needed."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(f"Circuit {self.name}: OPEN -> HALF_OPEN")
        return self._state
    
    def record_success(self):
        """Record successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0
    
    def record_failure(self):
        """Record failed call."""
        self._failure_count += 1
        self._last_failure_time = datetime.utcnow()
        
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN (failure during recovery)")
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit {self.name}: CLOSED -> OPEN (threshold reached)")
    
    def can_execute(self) -> bool:
        """Check if request can be executed."""
        state = self.state  # This may trigger state transition
        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.HALF_OPEN:
            return True
        else:  # OPEN
            return False


# Global circuit breakers registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _circuit_breakers[name]


async def retry_async(
    func: Callable,
    *args,
    max_retries: int = None,
    delay: float = None,
    backoff: float = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    circuit_breaker: Optional[CircuitBreaker] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs
) -> Any:
    """
    Execute async function with retry logic.
    
    Args:
        func: Async function to execute
        max_retries: Maximum retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Exception types to catch and retry
        circuit_breaker: Optional circuit breaker instance
        on_retry: Optional callback on retry (attempt, exception)
    
    Returns:
        Function result
    
    Raises:
        Last exception if all retries fail
    """
    max_retries = max_retries if max_retries is not None else config.MAX_RETRIES
    delay = delay if delay is not None else config.RETRY_DELAY
    backoff = backoff if backoff is not None else config.RETRY_BACKOFF
    
    last_exception = None
    current_delay = delay
    
    for attempt in range(max_retries + 1):
        # Check circuit breaker
        if circuit_breaker and not circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker {circuit_breaker.name} is OPEN, rejecting request")
            raise NetworkException(
                f"Service {circuit_breaker.name} unavailable (circuit breaker open)",
                {"circuit_state": circuit_breaker.state.value}
            )
        
        try:
            result = await func(*args, **kwargs)
            
            # Record success with circuit breaker
            if circuit_breaker:
                circuit_breaker.record_success()
            
            return result
            
        except exceptions as e:
            last_exception = e
            
            # Record failure with circuit breaker
            if circuit_breaker:
                circuit_breaker.record_failure()
            
            if attempt < max_retries:
                logger.warning(
                    f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}"
                )
                
                if on_retry:
                    on_retry(attempt + 1, e)
                
                await asyncio.sleep(current_delay)
                current_delay *= backoff
            else:
                logger.error(
                    f"All {max_retries} retries failed for {func.__name__}: {e}"
                )
    
    raise last_exception


def with_retry(
    max_retries: int = None,
    delay: float = None,
    backoff: float = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    circuit_breaker_name: Optional[str] = None
):
    """
    Decorator for adding retry logic to async functions.
    
    Usage:
        @with_retry(max_retries=3, exceptions=(NetworkException,))
        async def call_api():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cb = get_circuit_breaker(circuit_breaker_name) if circuit_breaker_name else None
            return await retry_async(
                func, *args,
                max_retries=max_retries,
                delay=delay,
                backoff=backoff,
                exceptions=exceptions,
                circuit_breaker=cb,
                **kwargs
            )
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry operations with cleanup.
    Useful for operations that need cleanup on failure.
    """
    
    def __init__(
        self,
        operation_name: str,
        max_retries: int = None,
        cleanup_func: Optional[Callable] = None
    ):
        self.operation_name = operation_name
        self.max_retries = max_retries or config.MAX_RETRIES
        self.cleanup_func = cleanup_func
        self.attempt = 0
        self.last_error = None
    
    async def __aenter__(self):
        self.attempt += 1
        logger.debug(f"Starting {self.operation_name} (attempt {self.attempt})")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.last_error = exc_val
            logger.warning(f"{self.operation_name} failed (attempt {self.attempt}): {exc_val}")
            
            if self.cleanup_func and self.attempt >= self.max_retries:
                logger.info(f"Running cleanup for {self.operation_name}")
                try:
                    if asyncio.iscoroutinefunction(self.cleanup_func):
                        await self.cleanup_func()
                    else:
                        self.cleanup_func()
                except Exception as cleanup_error:
                    logger.error(f"Cleanup failed for {self.operation_name}: {cleanup_error}")
            
            return False  # Re-raise exception
        
        logger.debug(f"{self.operation_name} completed successfully (attempt {self.attempt})")
        return False
