"""
ReadFlow AI — application factory.

Responsibilities:
  - Wire together Flask extensions (CSRF, rate limiter).
  - Register all blueprints.
  - Register the before_request hook that loads the current user and their
    settings into Flask's g object (fixes global theme application).
  - Add a `markdown` Jinja2 filter for rendering AI output as HTML.
  - Register error handlers.

Usage:
  Development : python app.py
  Production  : gunicorn app:app
"""

import logging
import os

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, CSRFError

from auth import load_logged_in_user
from config import Config
from db import close_db, init_db

# Load .env in development so developers don't have to set env vars manually.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Extensions ────────────────────────────────────────────────────────────────

csrf    = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


# ── Factory ───────────────────────────────────────────────────────────────────

def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # ── Extensions ────────────────────────────────────────────────────────────
    csrf.init_app(app)
    limiter.init_app(app)

    # ── Teardown & before-request ─────────────────────────────────────────────
    app.teardown_appcontext(close_db)
    app.before_request(load_logged_in_user)

    # ── Jinja2 filters ────────────────────────────────────────────────────────
    _register_template_filters(app)

    # ── Database ──────────────────────────────────────────────────────────────
    with app.app_context():
        init_db()

    # ── Blueprints ────────────────────────────────────────────────────────────
    _register_blueprints(app)

    # ── Error handlers ────────────────────────────────────────────────────────
    _register_error_handlers(app)

    return app


def _register_blueprints(app: Flask) -> None:
    from blueprints.auth_bp        import auth_bp
    from blueprints.main_bp        import main_bp
    from blueprints.library_bp     import library_bp
    from blueprints.annotations_bp import annotations_bp
    from blueprints.history_bp     import history_bp
    from blueprints.search_bp      import search_bp
    from blueprints.prefs_bp       import prefs_bp
    from blueprints.ai_bp          import ai_bp
    from blueprints.api_bp         import api_bp

    # Apply strict rate limits to authentication endpoints only
    limiter.limit("10 per minute")(auth_bp)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(annotations_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(prefs_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(api_bp)


def _register_template_filters(app: Flask) -> None:
    """Register custom Jinja2 filters."""
    try:
        import markdown as _md

        def markdown_filter(text: str) -> str:
            """Convert a Markdown string to safe HTML for use with |safe."""
            return _md.markdown(
                text or "",
                extensions=["nl2br", "fenced_code", "tables"],
            )

        app.jinja_env.filters["markdown"] = markdown_filter
    except ImportError:
        # Markdown package missing — fall back to plain <pre> rendering
        app.jinja_env.filters["markdown"] = lambda t: f"<pre>{t}</pre>"


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf(error):
        flash("Your form session expired. Please try again.", "error")
        return redirect(request.referrer or url_for("main.index"))

    @app.errorhandler(413)
    def handle_too_large(_error):
        flash("File is too large. Maximum upload size is 16 MB.", "error")
        return redirect(url_for("library.index"))

    @app.errorhandler(429)
    def handle_rate_limit(_error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(404)
    def handle_404(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def handle_500(_error):
        app.logger.exception("Unhandled 500 error")
        return render_template("errors/500.html"), 500


# ── Entry point ───────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") != "production")
