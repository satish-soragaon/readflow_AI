"""
Authentication helpers for ReadFlow AI.

Exposes:
  - load_logged_in_user()   — before_request hook that populates g.user and
                               g.user_settings so every template has access
                               to the current user and their theme preference.
  - login_required()        — view decorator.
  - hash_password()         — Werkzeug pbkdf2 wrapper.
  - verify_password()       — constant-time comparison wrapper.
"""

from functools import wraps

from flask import g, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_or_create_default_user, get_or_create_user_settings, query_one


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def load_logged_in_user() -> None:
    """
    Populate g.user and g.user_settings on every request.

    In no-auth mode the app auto-logs in as the default local user so there is
    no login screen.  Storing user_settings in g means the theme is available
    in base.html on every page (not just settings/reader).
    """
    user_id = session.get("user_id")

    if not user_id:
        # Auto-login: find or create the default user and pin it to the session
        default_user = get_or_create_default_user()
        if default_user:
            session["user_id"] = default_user["id"]
            user_id = default_user["id"]

    if user_id:
        g.user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
        g.user_settings = get_or_create_user_settings(user_id) if g.user else None
    else:
        g.user = None
        g.user_settings = None


def login_required(view):
    """No-op in no-auth mode — every request is already logged in."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)
    return wrapped_view
