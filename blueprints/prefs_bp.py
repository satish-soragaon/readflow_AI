"""
Preferences blueprint — /settings (user-configurable defaults).
"""

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from auth import login_required
from db import transaction

prefs_bp = Blueprint("prefs", __name__)

_VALID_MODES = {"word", "chunk", "sentence", "line"}
_VALID_THEMES = {"dark", "light"}
_VALID_WPMS = {100, 200, 300, 450, 600, 800, 1000}


@prefs_bp.route("/settings", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        # Validate and sanitise each field server-side even though the
        # HTML form already constrains choices (never trust client input).
        raw_wpm   = request.form.get("default_wpm", "200")
        raw_mode  = request.form.get("default_mode", "word")
        raw_theme = request.form.get("theme", "dark")
        raw_font  = request.form.get("font_size", "100")

        try:
            default_wpm = int(raw_wpm)
            if default_wpm not in _VALID_WPMS:
                default_wpm = 200
        except ValueError:
            default_wpm = 200

        default_mode = raw_mode if raw_mode in _VALID_MODES else "word"
        theme        = raw_theme if raw_theme in _VALID_THEMES else "dark"

        try:
            font_size = max(80, min(140, int(raw_font)))
        except ValueError:
            font_size = 100

        smart_pause = 1 if request.form.get("smart_pause_enabled") else 0

        with transaction() as db:
            db.execute(
                """
                UPDATE settings
                SET    default_wpm = ?, default_mode = ?, smart_pause_enabled = ?,
                       theme = ?, font_size = ?, updated_at = CURRENT_TIMESTAMP
                WHERE  user_id = ?
                """,
                (default_wpm, default_mode, smart_pause, theme, font_size, session["user_id"]),
            )

        flash("Settings saved.", "success")
        return redirect(url_for("prefs.index"))

    return render_template("settings.html", settings=g.user_settings)
