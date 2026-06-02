"""
BCETD Flask Application Factory.
Creates the Flask app with all routes registered.
"""

from flask import Flask
from app.config import get_config


def create_app(config_class=None):
    """Create and configure the Flask application."""

    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    # Load configuration
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # ── Register Blueprints (routes) ──
    from app.routes.chat import chat_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")

    # ── Health check endpoint ──
    @app.route("/health")
    def health():
        return {"status": "ok", "service": "bcetd-frontend-python"}, 200

    return app
