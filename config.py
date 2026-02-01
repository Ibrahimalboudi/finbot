"""
Application configuration with environment variable loading.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""

    # Paths
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv(
        "TELEGRAM_BOT_TOKEN", "8504066553:AAGlJoZUdJzP7NRXgHw6syhjW-deqZidM_Q")
    TELEGRAM_WEBHOOK_URL: str = os.getenv("TELEGRAM_WEBHOOK_URL", "")

    # Ichancy API
    ICHANCY_API_URL: str = os.getenv(
        "ICHANCY_API_URL", "https://dehost.alidoom.org/ichancy/api/api.php")
    ICHANCY_USERNAME: str = os.getenv("ICHANCY_USERNAME", "kkk")
    ICHANCY_PASSWORD: str = os.getenv("ICHANCY_PASSWORD", "test123")
    ICHANCY_TIMEOUT: int = int(os.getenv("ICHANCY_TIMEOUT", "15"))

    # Flask Admin
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "123456")
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bot.db")

    # Payment
    PAYMENT_TEST_MODE: str = os.getenv("PAYMENT_TEST_MODE", "True")

    # Retry settings
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: float = float(os.getenv("RETRY_DELAY", "1.0"))
    RETRY_BACKOFF: float = float(os.getenv("RETRY_BACKOFF", "2.0"))

    @classmethod
    def ensure_data_dir(cls):
        """Ensure data directory exists."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_payment_test_mode(cls) -> bool:
        """Check if payment system is in test mode."""
        return cls.PAYMENT_TEST_MODE == "0x01"


config = Config()
