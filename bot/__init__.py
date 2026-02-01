"""
Telegram bot module.
"""
from bot.handlers import setup_handlers
from bot.keyboards import keyboards
from bot.middlewares import UserMiddleware, RateLimitMiddleware, create_middleware_chain

__all__ = [
    "setup_handlers",
    "keyboards",
    "UserMiddleware",
    "RateLimitMiddleware",
    "create_middleware_chain"
]
