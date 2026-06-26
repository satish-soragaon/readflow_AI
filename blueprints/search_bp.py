"""
Search blueprint — full-text search across documents, notes, and history.

Uses SQLite FTS5 (documents_fts / notes_fts virtual tables) for documents
and notes, and a LIKE query for session history (which is short and not
indexed by FTS).

The FTS query wraps the user's input in double-quotes to perform an exact
phrase match; special characters are escaped to avoid FTS5 syntax errors.
"""

import logging

from flask import Blueprint, render_template, request, session

from auth import login_required
from db import get_db, query_all

log = logging.getLogger(__name__)

search_bp = Blueprint("search", __name__)

_MAX_RESULTS = 30  # cap per category to keep the page snappy


@search_bp.route("/search")
@login_required
def index():
    query   = request.args.get("q", "").strip()
    results = {"documents": [], "notes": [], "history": []}

    if query:
        user_id = session["user_id"]
        results["documents"] = _search_documents(user_id, query)
        results["notes"]     = _search_notes(user_id, query)
        results["history"]   = _search_history(user_id, query)

    return render_template("search.html", q=query, results=results)


# ── Private helpers ───────────────────────────────────────────────────────────

def _fts_term(raw: str) -> str:
    """
    Convert a raw user query into a safe FTS5 MATCH expression.

    Strips double-quotes from the input (they would break the FTS5 parser)
    and wraps the result in quotes for an exact phrase match, then appends
    a wildcard so "read" also matches "reading".
    """
    safe = raw.replace('"', "").strip()
    if not safe:
        return '""'
    return f'"{safe}"*'


def _search_documents(user_id: int, query: str) -> list:
    try:
        rows = get_db().execute(
            """
            SELECT d.*
            FROM   documents d
            JOIN   documents_fts fts ON fts.rowid = d.id
            WHERE  d.user_id = ?
              AND  documents_fts MATCH ?
            ORDER  BY rank
            LIMIT  ?
            """,
            (user_id, _fts_term(query), _MAX_RESULTS),
        ).fetchall()
        return rows
    except Exception:
        # FTS table absent on very old DB — graceful LIKE fallback
        log.debug("FTS5 unavailable for documents; falling back to LIKE search.")
        like = f"%{query}%"
        return query_all(
            "SELECT * FROM documents WHERE user_id = ? AND (title LIKE ? OR content LIKE ?) "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, like, like, _MAX_RESULTS),
        )


def _search_notes(user_id: int, query: str) -> list:
    try:
        rows = get_db().execute(
            """
            SELECT n.*, d.title AS document_title
            FROM   notes n
            JOIN   notes_fts fts  ON fts.rowid = n.id
            JOIN   documents d    ON d.id = n.document_id
            WHERE  n.user_id = ?
              AND  notes_fts MATCH ?
            ORDER  BY rank
            LIMIT  ?
            """,
            (user_id, _fts_term(query), _MAX_RESULTS),
        ).fetchall()
        return rows
    except Exception:
        log.debug("FTS5 unavailable for notes; falling back to LIKE search.")
        like = f"%{query}%"
        return query_all(
            """
            SELECT n.*, d.title AS document_title
            FROM   notes n JOIN documents d ON d.id = n.document_id
            WHERE  n.user_id = ? AND n.body LIKE ?
            ORDER  BY n.created_at DESC LIMIT ?
            """,
            (user_id, like, _MAX_RESULTS),
        )


def _search_history(user_id: int, query: str) -> list:
    like = f"%{query}%"
    return query_all(
        "SELECT * FROM reading_sessions WHERE user_id = ? AND document_name LIKE ? "
        "ORDER BY started_at DESC LIMIT ?",
        (user_id, like, _MAX_RESULTS),
    )
