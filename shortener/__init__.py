"""
Flask URL shortener application factory.
"""

from pathlib import Path

from flask import Flask

from .config import Config
from . import db as db_module
from .ratelimiter import RateLimiter

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(config_object: type = Config) -> Flask:
    # templates/ and static/ live at the project root, one level above
    # this package, so point Flask at them explicitly.
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.from_object(config_object)

    # Database (sqlite) setup + per-request connection handling.
    db_module.init_app(app)

    # Manual, dependency-free rate limiter (per IP, sliding window).
    app.rate_limiter = RateLimiter(
        max_requests=app.config["RATE_LIMIT_MAX"],
        window_seconds=app.config["RATE_LIMIT_WINDOW"],
    )

    from .routes import bp as routes_bp

    app.register_blueprint(routes_bp)

    return app
