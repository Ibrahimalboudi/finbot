"""
Admin authentication module.
"""
import bcrypt
from functools import wraps
from flask import session, redirect, url_for, request, flash
from typing import Optional

from config import config
from db import db
from utils.logger import get_logger

logger = get_logger("admin_auth")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def get_admin_user(username: str) -> Optional[dict]:
    """Get admin user from database."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM admin_users WHERE username = ? AND is_active = 1",
            (username,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
    return None


async def create_admin_user(username: str, password: str) -> bool:
    """Create a new admin user."""
    password_hash = hash_password(password)
    try:
        async with db.transaction() as conn:
            await conn.execute(
                "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                (username, password_hash)
            )
        logger.info(f"Created admin user: {username}")
        return True
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        return False


async def authenticate_admin(username: str, password: str) -> bool:
    """
    Authenticate admin user.
    Falls back to config credentials if no DB users exist.
    """
    # Try database first
    admin = await get_admin_user(username)
    if admin:
        if verify_password(password, admin["password_hash"]):
            logger.audit_security_event("ADMIN_LOGIN_SUCCESS", user_id=admin["id"])
            return True
        logger.audit_security_event("ADMIN_LOGIN_FAILED", user_id=admin["id"])
        return False
    
    # Fallback to config credentials (for initial setup)
    if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
        logger.audit_security_event("ADMIN_LOGIN_CONFIG", ip_address=request.remote_addr)
        return True
    
    logger.audit_security_event(
        "ADMIN_LOGIN_FAILED",
        ip_address=request.remote_addr,
        username=username
    )
    return False


def login_required(f):
    """Decorator to require admin login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("admin.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def is_logged_in() -> bool:
    """Check if admin is logged in."""
    return session.get("admin_logged_in", False)
