"""
Create a new admin user.
Usage: python scripts/create_admin.py <username> <password>
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db
from admin.auth import create_admin_user
from utils.logger import get_logger

logger = get_logger("create_admin")


async def main(username: str, password: str):
    """Create admin user."""
    # Initialize database
    await db.initialize()
    
    # Create user
    success = await create_admin_user(username, password)
    
    if success:
        print(f"Admin user '{username}' created successfully!")
    else:
        print(f"Failed to create admin user '{username}'")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/create_admin.py <username> <password>")
        sys.exit(1)
    
    asyncio.run(main(sys.argv[1], sys.argv[2]))
