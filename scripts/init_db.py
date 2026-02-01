"""
Database initialization script.
Run this to create the database and initial admin user.
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from db import db
from admin.auth import create_admin_user, hash_password
from utils.logger import get_logger

logger = get_logger("init_db")


async def init_database():
    """Initialize database with schema and default admin user."""
    logger.info("Initializing database...")
    
    # Ensure data directory exists
    config.ensure_data_dir()
    
    # Initialize database schema
    await db.initialize()
    logger.info(f"Database created at: {config.DATABASE_PATH}")
    
    # Create default admin user if not exists
    async with db.connection() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as count FROM admin_users")
        row = await cursor.fetchone()
        
        if row["count"] == 0:
            # Create default admin from config
            success = await create_admin_user(
                config.ADMIN_USERNAME,
                config.ADMIN_PASSWORD
            )
            if success:
                logger.info(f"Created default admin user: {config.ADMIN_USERNAME}")
            else:
                logger.error("Failed to create default admin user")
        else:
            logger.info(f"Admin users already exist: {row['count']}")
    
    logger.info("Database initialization complete!")


def main():
    """Run initialization."""
    asyncio.run(init_database())


if __name__ == "__main__":
    main()
