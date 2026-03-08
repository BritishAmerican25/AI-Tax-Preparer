"""AI Tax Preparer – application factory."""

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import get_config

limiter = Limiter(key_func=get_remote_address)


def create_app(config_override: dict | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(get_config())

    if config_override:
        app.config.update(config_override)

    limiter.init_app(app)

    from app.routes.tax import tax_bp

    app.register_blueprint(tax_bp, url_prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "AI-Tax-Preparer"}

    return app
