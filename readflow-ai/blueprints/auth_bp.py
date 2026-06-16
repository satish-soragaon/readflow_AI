"""
Authentication blueprint — /register, /login, /logout.

Rate limits are applied at the blueprint level so they cover every
auth endpoint without needing per-route decorators.
"""

from flask import Blueprint, redirect, session, url_for

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # Auth is disabled — redirect straight to the library.
    return redirect(url_for("library.index"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Auth is disabled — redirect straight to the library.
    return redirect(url_for("library.index"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Clearing the session just causes auto-login on the next request.
    session.clear()
    return redirect(url_for("library.index"))
