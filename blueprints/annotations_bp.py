"""
Annotations blueprint — bookmarks, notes, and highlights (full CRUD).

All write endpoints return JSON so the reader page can update companion
cards via fetch() without a full page reload.

DELETE endpoints use the HTTP DELETE method; only JavaScript calls them,
so no HTML-form fallback is needed (the reader already requires JS).
"""

import logging

from flask import Blueprint, abort, g, jsonify, request, session

from auth import login_required
from db import query_one, transaction
from document_utils import excerpt_at_position

log = logging.getLogger(__name__)

annotations_bp = Blueprint("annotations", __name__)


# ── Guard helper ─────────────────────────────────────────────────────────────

def _own_document(document_id: int):
    """Return the document or 404 if it doesn't belong to the logged-in user."""
    doc = query_one(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (document_id, session["user_id"]),
    )
    if doc is None:
        abort(404)
    return doc


def _clamp_position(value, word_count: int) -> int:
    """Keep position within the valid word range."""
    try:
        return max(0, min(int(value), max(word_count, 0)))
    except (TypeError, ValueError):
        return 0


# ── Bookmarks ─────────────────────────────────────────────────────────────────

@annotations_bp.route("/documents/<int:document_id>/bookmarks", methods=["POST"])
@login_required
def add_bookmark(document_id):
    document = _own_document(document_id)
    data     = request.get_json(silent=True) or request.form

    position = _clamp_position(data.get("position", 0), document["word_count"])
    label    = (data.get("label") or f"Word {position}").strip()[:200]

    with transaction() as db:
        cursor = db.execute(
            "INSERT INTO bookmarks (user_id, document_id, label, position) VALUES (?, ?, ?, ?)",
            (session["user_id"], document_id, label, position),
        )
        bookmark_id = cursor.lastrowid

    return jsonify({
        "ok": True,
        "item": {"id": bookmark_id, "label": label, "position": position},
    })


@annotations_bp.route(
    "/documents/<int:document_id>/bookmarks/<int:bookmark_id>",
    methods=["DELETE"],
)
@login_required
def delete_bookmark(document_id, bookmark_id):
    _own_document(document_id)
    with transaction() as db:
        db.execute(
            "DELETE FROM bookmarks WHERE id = ? AND user_id = ?",
            (bookmark_id, session["user_id"]),
        )
    return jsonify({"ok": True})


# ── Notes ─────────────────────────────────────────────────────────────────────

@annotations_bp.route("/documents/<int:document_id>/notes", methods=["POST"])
@login_required
def add_note(document_id):
    document = _own_document(document_id)
    data     = request.get_json(silent=True) or request.form

    position = _clamp_position(data.get("position", 0), document["word_count"])
    body     = (data.get("body") or "").strip()

    if not body:
        return jsonify({"ok": False, "error": "Note body cannot be empty."}), 400

    with transaction() as db:
        cursor = db.execute(
            "INSERT INTO notes (user_id, document_id, position, body) VALUES (?, ?, ?, ?)",
            (session["user_id"], document_id, position, body),
        )
        note_id = cursor.lastrowid

    return jsonify({
        "ok": True,
        "item": {"id": note_id, "position": position, "body": body},
    })


@annotations_bp.route(
    "/documents/<int:document_id>/notes/<int:note_id>",
    methods=["DELETE"],
)
@login_required
def delete_note(document_id, note_id):
    _own_document(document_id)
    with transaction() as db:
        db.execute(
            "DELETE FROM notes WHERE id = ? AND user_id = ?",
            (note_id, session["user_id"]),
        )
    return jsonify({"ok": True})


# ── Highlights ────────────────────────────────────────────────────────────────

@annotations_bp.route("/documents/<int:document_id>/highlights", methods=["POST"])
@login_required
def add_highlight(document_id):
    document = _own_document(document_id)
    data     = request.get_json(silent=True) or request.form

    position = _clamp_position(data.get("position", 0), document["word_count"])
    text     = (data.get("text") or "").strip()

    # Fall back to the excerpt around the current position if no text was given
    if not text and document["content"]:
        text = excerpt_at_position(document["content"], position)

    if not text:
        return jsonify({"ok": False, "error": "No text to highlight."}), 400

    with transaction() as db:
        cursor = db.execute(
            """
            INSERT INTO highlights
                (user_id, document_id, start_position, end_position, text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session["user_id"], document_id, position, position, text),
        )
        highlight_id = cursor.lastrowid

    return jsonify({
        "ok": True,
        "item": {"id": highlight_id, "position": position, "text": text},
    })


@annotations_bp.route(
    "/documents/<int:document_id>/highlights/<int:highlight_id>",
    methods=["DELETE"],
)
@login_required
def delete_highlight(document_id, highlight_id):
    _own_document(document_id)
    with transaction() as db:
        db.execute(
            "DELETE FROM highlights WHERE id = ? AND user_id = ?",
            (highlight_id, session["user_id"]),
        )
    return jsonify({"ok": True})
