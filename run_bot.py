"""
Telegram bot entry point.
Run this to start the bot in polling mode.
"""
import asyncio
import signal
from telegram.ext import Application

from config import config
from db import db
from bot import setup_handlers
from services import ichancy_service
from utils.logger import get_logger

logger = get_logger("run_bot")


async def post_init(application: Application) -> None:
    """Post-initialization hook."""
    # Initialize database
    await db.initialize()
    logger.info("Database initialized")
    
    # Check Ichancy API status
    try:
        status = await ichancy_service.check_status()
        if status.success:
            logger.info("Ichancy API is online")
        else:
            logger.warning(f"Ichancy API check failed: {status.error}")
    except Exception as e:
        logger.warning(f"Could not reach Ichancy API: {e}")


async def post_shutdown(application: Application) -> None:
    """Post-shutdown hook."""
    # Close Ichancy client
    await ichancy_service.close()
    logger.info("Bot shutdown complete")


def main():
    """Run the bot."""
    # Validate configuration
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        return
    
    logger.info("Starting Telegram bot...")
    
    # Create application
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Setup handlers
    setup_handlers(application)
    
    # Run bot
    if config.TELEGRAM_WEBHOOK_URL:
        # Webhook mode (for production)
        logger.info(f"Running in webhook mode: {config.TELEGRAM_WEBHOOK_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=8443,
            url_path="webhook/telegram",
            webhook_url=f"{config.TELEGRAM_WEBHOOK_URL}/webhook/telegram",
        )
    else:
        # Polling mode (for development)
        logger.info("Running in polling mode")
        
        # Manually drop webhook if it exists to avoid Conflict
        async def cleanup_webhook():
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Existing webhook removed and updates dropped")
            
        loop = asyncio.get_event_loop()
        loop.run_until_complete(cleanup_webhook())
        
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            close_loop=False,
            stop_signals=None
        )


if __name__ == "__main__":
    main()
