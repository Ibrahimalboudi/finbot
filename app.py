"""
Flask application entry point.
Provides admin dashboard and webhook endpoints.
"""
import asyncio
from flask import Flask, request, jsonify

from config import config
from db import db
from admin import admin_bp
from utils.logger import get_logger

logger = get_logger("app")


def create_app() -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Configuration
    app.secret_key = config.FLASK_SECRET_KEY
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    
    # Register blueprints
    app.register_blueprint(admin_bp)
    
    # Initialize database on first request
    @app.before_request
    def initialize():
        if not getattr(app, "_db_initialized", False):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(db.initialize())
            loop.close()
            setattr(app, "_db_initialized", True)
    
    # Health check endpoint
    @app.route("/health")
    def health():
        return jsonify({"status": "healthy", "service": "finance-bot"})
    
    # Webhook endpoint for Telegram (if using webhooks)
    @app.route("/webhook/telegram", methods=["POST"])
    def telegram_webhook():
        """
        Telegram webhook endpoint.
        Note: This is handled by python-telegram-bot's webhook mode.
        This endpoint is here for reference/manual handling if needed.
        """
        # In production, the telegram-bot library handles this
        return jsonify({"status": "received"})
    
    # Payment webhook endpoints (for future integration)
    @app.route("/webhook/syriatel", methods=["POST"])
    def syriatel_webhook():
        """Webhook for Syriatel Cash payment notifications."""
        data = request.json
        logger.info(f"Syriatel webhook received: {data}")
        # TODO: Implement actual verification when API is available
        return jsonify({"status": "received"})
    
    @app.route("/webhook/sham", methods=["POST"])
    def sham_webhook():
        """Webhook for Sham Cash payment notifications."""
        data = request.json
        logger.info(f"Sham Cash webhook received: {data}")
        # TODO: Implement actual verification when API is available
        return jsonify({"status": "received"})
    
    # Root redirect to admin
    @app.route("/")
    def root():
        from flask import redirect, url_for
        return redirect(url_for("admin.login"))
    
    logger.info("Flask application created")
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    # Run in development mode
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
