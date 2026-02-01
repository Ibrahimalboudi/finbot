"""
Telegram bot middleware for user management and rate limiting.
"""
from typing import Callable, Any, Awaitable
from datetime import datetime
from telegram import Update
from telegram.ext import BaseHandler, ContextTypes

from db import db, User, UserState, UserRepository
from utils.logger import get_logger

logger = get_logger("middleware")


class UserMiddleware:
    """
    Middleware to ensure user exists in database.
    Creates user record on first interaction.
    """
    
    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
    ) -> Any:
        """Process update and ensure user exists."""
        
        # Get user from update
        user = update.effective_user
        if not user:
            return await handler(update, context)
        
        # Check/create user in database
        db_user = await UserRepository.get_by_id(user.id)
        
        if not db_user:
            # Create new user
            db_user = User(
                id=user.id,
                telegram_username=user.username,
                state=UserState.ACTIVE
            )
            db_user = await UserRepository.create(db_user)
            logger.info(f"New user created: {user.id} (@{user.username})")
        else:
            # Update username if changed
            if db_user.telegram_username != user.username:
                db_user.telegram_username = user.username
                await UserRepository.update(db_user)
        
        # Store user in context for handlers
        context.user_data["db_user"] = db_user
        
        # Check if user is blocked
        if db_user.state == UserState.BLOCKED:
            if update.message:
                await update.message.reply_text(
                    "Your account has been blocked. Please contact support."
                )
            return None
        
        return await handler(update, context)


class RateLimitMiddleware:
    """
    Simple rate limiting middleware.
    Prevents spam and abuse.
    """
    
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, list[datetime]] = {}
    
    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
    ) -> Any:
        """Check rate limit before processing."""
        
        user = update.effective_user
        if not user:
            return await handler(update, context)
        
        now = datetime.utcnow()
        user_id = user.id
        
        # Initialize user's request list
        if user_id not in self._requests:
            self._requests[user_id] = []
        
        # Clean old requests
        cutoff = datetime.utcnow()
        self._requests[user_id] = [
            ts for ts in self._requests[user_id]
            if (now - ts).total_seconds() < self.window_seconds
        ]
        
        # Check rate limit
        if len(self._requests[user_id]) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            if update.message:
                await update.message.reply_text(
                    "Too many requests. Please wait a moment before trying again."
                )
            return None
        
        # Record this request
        self._requests[user_id].append(now)
        
        return await handler(update, context)


class LoggingMiddleware:
    """
    Middleware to log all incoming updates.
    """
    
    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
    ) -> Any:
        """Log update and process."""
        
        user = update.effective_user
        user_info = f"{user.id} (@{user.username})" if user else "unknown"
        
        if update.message and update.message.text:
            logger.debug(f"Message from {user_info}: {update.message.text[:100]}")
        elif update.callback_query:
            logger.debug(f"Callback from {user_info}: {update.callback_query.data}")
        
        try:
            result = await handler(update, context)
            return result
        except Exception as e:
            logger.error(f"Error handling update from {user_info}: {e}", exc_info=True)
            raise


def create_middleware_chain(
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]:
    """
    Create a middleware chain for handlers.
    
    Usage:
        @create_middleware_chain
        async def my_handler(update, context):
            ...
    """
    user_middleware = UserMiddleware()
    rate_limit_middleware = RateLimitMiddleware()
    logging_middleware = LoggingMiddleware()
    
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        # Chain: Logging -> RateLimit -> User -> Handler
        return await logging_middleware(
            update, context,
            lambda u, c: rate_limit_middleware(
                u, c,
                lambda u2, c2: user_middleware(u2, c2, handler)
            )
        )
    
    return wrapped
