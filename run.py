"""
Combined runner for both Flask and Telegram bot.
Useful for development - runs both services in separate threads.
"""
import asyncio
import threading
import signal
import sys
from typing import Optional

from utils.logger import get_logger

logger = get_logger("runner")


class ServiceRunner:
    """Runs Flask and Telegram bot services."""
    
    def __init__(self):
        self.flask_thread: Optional[threading.Thread] = None
        self.bot_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
    
    def run_flask(self):
        """Run Flask in a thread."""
        from app import app
        # Replit needs host 0.0.0.0 for the proxy to work
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=True,
            use_reloader=False
        )
    
    def run_bot(self):
        """Run Telegram bot in a thread."""
        import asyncio
        from run_bot import main as bot_main
        
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # We need to monkeypatch run_polling or use a different entry point 
            # because run_polling tries to handle signals which only works in main thread
            from run_bot import main as bot_main
            bot_main()
        except Exception as e:
            logger.error(f"Bot thread error: {e}")
        finally:
            loop.close()
    
    def start(self, flask: bool = True, bot: bool = True):
        """
        Start services.
        
        Args:
            flask: Whether to start Flask server
            bot: Whether to start Telegram bot
        """
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        if flask:
            logger.info("Starting Flask server...")
            self.flask_thread = threading.Thread(target=self.run_flask, daemon=True)
            self.flask_thread.start()
        
        if bot:
            logger.info("Starting Telegram bot...")
            self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
            self.bot_thread.start()
        
        logger.info("All services started. Press Ctrl+C to stop.")
        
        # Wait for shutdown signal
        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(timeout=1.0)
        except (KeyboardInterrupt, SystemExit):
            self._shutdown.set()
        
        logger.info("Shutting down...")
        # Signal bot thread to stop if possible or just exit
        sys.exit(0)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self._shutdown.set()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Finance Bot services")
    parser.add_argument("--flask-only", action="store_true", help="Run only Flask server")
    parser.add_argument("--bot-only", action="store_true", help="Run only Telegram bot")
    args = parser.parse_args()
    
    runner = ServiceRunner()
    
    if args.flask_only:
        runner.start(flask=True, bot=False)
    elif args.bot_only:
        runner.start(flask=False, bot=True)
    else:
        runner.start(flask=True, bot=True)


if __name__ == "__main__":
    main()
