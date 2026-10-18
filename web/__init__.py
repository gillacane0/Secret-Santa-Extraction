"""The Secret Santa website: friends join a group themselves and see their match online."""

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db, views

PROJECT_DIR = Path(__file__).resolve().parent.parent


def create_app(config: dict | None = None) -> Flask:
    load_dotenv(PROJECT_DIR / ".env")
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        DATABASE=str(PROJECT_DIR / "instance" / "secret_santa.db"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=90),
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=True,
        MAX_CONTENT_LENGTH=1024 * 1024,  # backups are tiny
    )
    app.config.update(config or {})
    if not app.config["SECRET_KEY"]:
        # Still works, but everyone gets logged out whenever the site restarts.
        app.logger.warning("SECRET_KEY is not set, see the README.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)

    # Hosting services put the site behind a proxy that handles https.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
    db.init_app(app)
    app.register_blueprint(views.bp)
    app.after_request(_security_headers)
    return app


def _security_headers(response: Response) -> Response:
    response.headers["Referrer-Policy"] = "no-referrer"  # the links contain secret codes
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response
