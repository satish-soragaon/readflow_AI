"""
History blueprint — paginated reading sessions log.
"""

from flask import Blueprint, render_template, request, session

from auth import login_required
from db import query_all, query_one

history_bp = Blueprint("history", __name__)

_PER_PAGE = 25


@history_bp.route("/history")
@login_required
def index():
    page   = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * _PER_PAGE

    total = query_one(
        "SELECT COUNT(*) AS n FROM reading_sessions WHERE user_id = ?",
        (session["user_id"],),
    )["n"]

    sessions = query_all(
        """
        SELECT * FROM reading_sessions
        WHERE  user_id = ?
        ORDER  BY started_at DESC
        LIMIT  ? OFFSET ?
        """,
        (session["user_id"], _PER_PAGE, offset),
    )

    total_pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)

    return render_template(
        "history.html",
        sessions=sessions,
        page=page,
        total_pages=total_pages,
        total=total,
    )
