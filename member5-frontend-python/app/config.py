"""
BCETD Flask Application Configuration.
All settings are loaded from environment variables with sensible defaults.
"""

import os


class Config:
    """Base configuration."""

    # ── Flask ──
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "bcetd-dev-secret-change-in-prod")
    DEBUG = False
    TESTING = False

    # ── n8n Webhook URLs (internal Docker network) ──
    N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://n8n:5678")
    N8N_CHAT_WEBHOOK = os.getenv("N8N_CHAT_WEBHOOK", "/webhook/chat")
    N8N_ANALYTICS_SUMMARY = os.getenv("N8N_ANALYTICS_SUMMARY", "/webhook/analytics/summary")
    N8N_ANALYTICS_DAILY = os.getenv("N8N_ANALYTICS_DAILY", "/webhook/analytics/daily")
    N8N_ANALYTICS_CATEGORIES = os.getenv("N8N_ANALYTICS_CATEGORIES", "/webhook/analytics/categories")
    N8N_ANALYTICS_DOCUMENTS = os.getenv("N8N_ANALYTICS_DOCUMENTS", "/webhook/analytics/documents")
    N8N_ANALYTICS_HOURLY = os.getenv("N8N_ANALYTICS_HOURLY", "/webhook/analytics/hourly")

    # ── Request settings ──
    N8N_TIMEOUT = int(os.getenv("N8N_TIMEOUT", "30"))  # seconds
    MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "500"))

    # ── Session ──
    SESSION_ROTATE_SECONDS = int(os.getenv("SESSION_ROTATE_SECONDS", "3600"))  # 1 hour


class DevelopmentConfig(Config):
    DEBUG = True
    # In dev, n8n might be on localhost instead of Docker network
    N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    N8N_BASE_URL = "http://mock-n8n:5678"


# Map environment name to config class
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    """Return the appropriate config based on FLASK_ENV."""
    env = os.getenv("FLASK_ENV", "production")
    return config_map.get(env, ProductionConfig)
