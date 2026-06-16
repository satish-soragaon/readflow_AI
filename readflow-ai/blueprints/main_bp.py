"""
Main blueprint — landing page (/) and analytics dashboard (/dashboard).
"""

from flask import Blueprint, g, redirect, render_template, session, url_for

from auth import login_required
from db import query_all, query_one, reading_streak

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    # Always go straight to the dashboard — no login screen
    return redirect(url_for("main.dashboard"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]

    stats = query_one(
        """
        SELECT
            COUNT(DISTINCT document_id)                                         AS total_documents_read,
            COALESCE(SUM(words_read), 0)                                        AS total_words_read,
            COALESCE(SUM(duration_seconds), 0)                                  AS total_reading_time,
            COALESCE(ROUND(AVG(NULLIF(wpm, 0))), 0)                             AS average_wpm,
            COALESCE(MAX(wpm), 0)                                               AS highest_wpm,
            COALESCE(SUM(CASE WHEN completion_percentage >= 100 THEN 1 ELSE 0 END), 0)
                                                                                AS completed_sessions
        FROM reading_sessions
        WHERE user_id = ?
        """,
        (user_id,),
    )

    recent_docs = query_all(
        "SELECT * FROM documents WHERE user_id = ? ORDER BY updated_at DESC LIMIT 5",
        (user_id,),
    )

    # Last 7 days of reading activity for the bar chart
    chart_rows = query_all(
        """
        SELECT DATE(started_at) AS label, COALESCE(SUM(words_read), 0) AS value
        FROM   reading_sessions
        WHERE  user_id = ?
        GROUP  BY DATE(started_at)
        ORDER  BY label DESC
        LIMIT  7
        """,
        (user_id,),
    )

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_docs=recent_docs,
        streak=reading_streak(user_id),
        chart_rows=list(reversed(chart_rows)),
    )
