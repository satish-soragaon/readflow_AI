"""
AI tools blueprint — /documents/<id>/ai.

Renders AI-generated study artifacts (summary, flashcards, quiz, etc.)
The AI output is markdown; the template converts it to HTML with the
`markdown` filter registered in app.py.
"""

import logging

from flask import Blueprint, abort, render_template, request, session

from ai_providers import get_ai_provider
from auth import login_required
from db import query_one

log = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__)

_VALID_TASKS = {"summary", "takeaways", "flashcards", "quiz", "study_notes", "vocabulary"}


@ai_bp.route("/documents/<int:document_id>/ai", methods=["GET", "POST"])
@login_required
def ai_tools(document_id):
    document = query_one(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (document_id, session["user_id"]),
    )
    if document is None:
        abort(404)

    output = None
    task   = request.form.get("task", "summary")
    if task not in _VALID_TASKS:
        task = "summary"

    if request.method == "POST":
        provider = get_ai_provider()
        output   = provider.generate(task, document["content"] or "")
        log.info("AI task=%s provider=%s document_id=%d", task, provider.name, document_id)

    return render_template(
        "ai.html",
        document=document,
        output=output,
        task=task,
        provider_name=get_ai_provider().name,
    )
