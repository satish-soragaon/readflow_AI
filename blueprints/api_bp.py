"""
API blueprint — JSON endpoints consumed by reader.js.

/api/reader/progress (POST) — saves reading position and updates the
                              active reading session.
"""

import logging
from datetime import datetime

from flask import Blueprint, abort, jsonify, request, session

from auth import login_required
from db import query_one, transaction

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/reader/progress", methods=["POST"])
@login_required
def reader_progress():
    """
    Persist reading progress without a full page reload.

    Accepts JSON or form data.  All integer fields are validated and bounded
    to prevent storage of bogus values from a malformed request.
    """
    payload = request.get_json(silent=True) or request.form

    # Safely coerce every numeric field; return 400 if any are unparseable.
    try:
        document_id = int(payload.get("document_id", 0))
        session_id  = int(payload.get("session_id",  0))
        position    = int(payload.get("position",    0))
        wpm         = int(payload.get("wpm",         200))
        completion  = int(payload.get("completion",  0))
        duration    = int(payload.get("duration_seconds", 0))
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid numeric field: {exc}"}), 400

    # Clamp to sane ranges
    position   = max(0, position)
    wpm        = max(50, min(2000, wpm))
    completion = max(0, min(100, completion))
    duration   = max(0, duration)

    mode = str(payload.get("mode", "word"))[:20]

    # Verify the document belongs to the current user (prevents IDOR)
    document = query_one(
        "SELECT id, word_count FROM documents WHERE id = ? AND user_id = ?",
        (document_id, session["user_id"]),
    )
    if document is None:
        abort(403)

    position = min(position, document["word_count"])

    ended_at = datetime.utcnow().isoformat(timespec="seconds") if completion >= 100 else None

    with transaction() as db:
        db.execute(
            """
            UPDATE documents
            SET    last_position = ?, last_wpm = ?, last_mode = ?,
                   updated_at = CURRENT_TIMESTAMP
            WHERE  id = ? AND user_id = ?
            """,
            (position, wpm, mode, document_id, session["user_id"]),
        )
        db.execute(
            """
            UPDATE reading_sessions
            SET    duration_seconds = ?, wpm = ?, reading_mode = ?,
                   completion_percentage = ?, words_read = ?, ended_at = ?
            WHERE  id = ? AND user_id = ?
            """,
            (duration, wpm, mode, completion, position, ended_at,
             session_id, session["user_id"]),
        )

    return jsonify({"ok": True})
