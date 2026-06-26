"""
Library blueprint — document management and RSVP reader.

Routes:
  GET/POST /library              — list documents; upload or paste new one
  GET      /documents/<id>/read  — open the RSVP reader
  POST     /documents/<id>/rename
  POST     /documents/<id>/delete
"""

import logging

from flask import (
    Blueprint, abort, current_app, flash, g,
    redirect, render_template, request, session, url_for,
)

from auth import login_required
from db import (
    get_or_create_reading_session, query_all, query_one, transaction,
)
from document_utils import (
    allowed_file, clean_text_for_reader, delete_stored_file,
    extract_text_for_file, normalize_text_for_count, save_upload, word_count,
)

log = logging.getLogger(__name__)

library_bp = Blueprint("library", __name__)

_PER_PAGE = 20  # documents shown per page in library


# ── Library ───────────────────────────────────────────────────────────────────

@library_bp.route("/library", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        document_id = _create_document_from_request()
        if document_id:
            return redirect(url_for("library.read_document", document_id=document_id))
        return redirect(url_for("library.index"))

    # Paginated document list
    page = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * _PER_PAGE

    total = query_one(
        "SELECT COUNT(*) AS n FROM documents WHERE user_id = ?",
        (session["user_id"],),
    )["n"]

    documents = query_all(
        "SELECT * FROM documents WHERE user_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (session["user_id"], _PER_PAGE, offset),
    )

    total_pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)

    return render_template(
        "library.html",
        documents=documents,
        page=page,
        total_pages=total_pages,
        total=total,
    )


# ── RSVP reader ───────────────────────────────────────────────────────────────

@library_bp.route("/documents/<int:document_id>/read")
@login_required
def read_document(document_id):
    document   = _get_user_document(document_id)
    user_settings = g.user_settings  # already loaded in before_request

    session_id = get_or_create_reading_session(
        document, user_settings, session["user_id"]
    )

    bookmarks = query_all(
        "SELECT * FROM bookmarks WHERE user_id = ? AND document_id = ? ORDER BY position",
        (session["user_id"], document_id),
    )
    notes = query_all(
        "SELECT * FROM notes WHERE user_id = ? AND document_id = ? ORDER BY created_at DESC",
        (session["user_id"], document_id),
    )
    highlights = query_all(
        "SELECT * FROM highlights WHERE user_id = ? AND document_id = ? ORDER BY created_at DESC",
        (session["user_id"], document_id),
    )

    return render_template(
        "reader.html",
        document=document,
        text=document["content"],
        source_label=document["title"],
        word_count=document["word_count"],
        session_id=session_id,
        bookmarks=bookmarks,
        notes=notes,
        highlights=highlights,
    )


# ── Document CRUD ─────────────────────────────────────────────────────────────

@library_bp.route("/documents/<int:document_id>/rename", methods=["POST"])
@login_required
def rename_document(document_id):
    _get_user_document(document_id)
    title = request.form.get("title", "").strip()
    if title:
        with transaction() as db:
            db.execute(
                "UPDATE documents SET title = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND user_id = ?",
                (title, document_id, session["user_id"]),
            )
        flash("Document renamed.", "success")
    return redirect(url_for("library.index"))


@library_bp.route("/documents/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_document(document_id):
    document = _get_user_document(document_id)

    # Delete the physical upload file before removing the DB row so we don't
    # end up with orphaned files if the DB delete fails.
    delete_stored_file(
        document["stored_filename"],
        current_app.config["UPLOAD_DIR"],
    )

    with transaction() as db:
        db.execute(
            "DELETE FROM documents WHERE id = ? AND user_id = ?",
            (document_id, session["user_id"]),
        )

    flash("Document deleted.", "success")
    return redirect(url_for("library.index"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_document(document_id: int):
    """Return the document or 404 if it doesn't exist / belong to the user."""
    doc = query_one(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (document_id, session["user_id"]),
    )
    if doc is None:
        abort(404)
    return doc


def _create_document_from_request():
    """
    Parse the incoming form, extract text, persist the document, and return
    its new id.  Returns None (with a flash message) on any failure.
    """
    uploaded_file = request.files.get("document")
    pasted_text   = request.form.get("manual_text", "").strip()
    title         = request.form.get("title", "").strip()
    text          = ""
    original_filename = stored_filename = file_type = None
    source_type   = "manual"

    try:
        if uploaded_file and uploaded_file.filename:
            if not allowed_file(
                uploaded_file.filename, current_app.config["ALLOWED_EXTENSIONS"]
            ):
                flash(
                    "Unsupported file type. Please upload PDF, DOCX, TXT, JPG, JPEG, PNG, or WEBP.",
                    "error",
                )
                return None

            original_filename, stored_filename, file_type, saved_path = save_upload(
                uploaded_file, current_app.config["UPLOAD_DIR"]
            )
            text = extract_text_for_file(saved_path, file_type)
            source_type = "upload"
            title = title or original_filename

        elif pasted_text:
            text  = pasted_text
            title = title or "Pasted Text"

        else:
            flash("Please upload a file or paste some text.", "error")
            return None

        reader_text = clean_text_for_reader(text)
        if not normalize_text_for_count(reader_text):
            flash("No readable text was found in that document.", "error")
            return None

        with transaction() as db:
            cursor = db.execute(
                """
                INSERT INTO documents
                    (user_id, title, original_filename, stored_filename,
                     file_type, source_type, content, word_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    title,
                    original_filename,
                    stored_filename,
                    file_type,
                    source_type,
                    reader_text,
                    word_count(reader_text),
                ),
            )
            return cursor.lastrowid

    except Exception:
        log.exception("Document ingestion failed")
        flash(
            "We could not process that document. Please try a different file.",
            "error",
        )
        return None
