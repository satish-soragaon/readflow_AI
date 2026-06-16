"""
Document ingestion utilities for ReadFlow AI.

Handles file saving, text extraction dispatch, and text normalisation.
All file-system paths are Path objects; callers are responsible for
ensuring the upload directory exists (done by init_db on startup).
"""

import logging
import uuid
from pathlib import Path

from werkzeug.utils import secure_filename

from services.docx_service import extract_docx_text
from services.image_service import extract_image_text
from services.pdf_service import extract_pdf_text
from services.txt_service import extract_txt_text

log = logging.getLogger(__name__)

# Maps file extension → extraction function
EXTRACTORS = {
    "pdf":  extract_pdf_text,
    "docx": extract_docx_text,
    "txt":  extract_txt_text,
    "jpg":  extract_image_text,
    "jpeg": extract_image_text,
    "png":  extract_image_text,
    "webp": extract_image_text,
}


# ── File helpers ──────────────────────────────────────────────────────────────

def allowed_file(filename: str, allowed_extensions: frozenset) -> bool:
    return "." in filename and get_extension(filename) in allowed_extensions


def get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower()


def save_upload(uploaded_file, upload_dir: Path) -> tuple[str, str, str, Path]:
    """
    Save *uploaded_file* under a UUID-based name to prevent path-traversal
    and filename collisions.

    Returns (original_filename, stored_filename, extension, saved_path).
    """
    original_filename = secure_filename(uploaded_file.filename)
    extension = get_extension(original_filename)
    stored_filename = f"{uuid.uuid4().hex}.{extension}"
    saved_path = upload_dir / stored_filename
    uploaded_file.save(saved_path)
    return original_filename, stored_filename, extension, saved_path


def delete_stored_file(stored_filename: str | None, upload_dir: Path) -> None:
    """
    Remove the physical upload file when a document is deleted from the DB.
    Silently no-ops if the file is absent or stored_filename is None.
    """
    if not stored_filename:
        return
    path = upload_dir / stored_filename
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("Could not delete upload file: %s", path)


# ── Text extraction ───────────────────────────────────────────────────────────

def extract_text_for_file(file_path: Path, extension: str) -> str:
    """Dispatch extraction to the appropriate service for *extension*."""
    extractor = EXTRACTORS.get(extension)
    if extractor is None:
        raise ValueError(f"Unsupported file type: .{extension}")
    return extractor(file_path)


# ── Text normalisation ────────────────────────────────────────────────────────

def clean_text_for_reader(text: str) -> str:
    """
    Normalise line-endings and collapse intra-line whitespace while preserving
    paragraph breaks (single newlines between non-empty lines).
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)


def normalize_text_for_count(text: str) -> str:
    """Collapse all whitespace to single spaces for word-count purposes."""
    return " ".join(text.split())


def word_count(text: str) -> int:
    return len(normalize_text_for_count(text).split())


def excerpt_at_position(text: str, position: int, radius: int = 18) -> str:
    """Return ~36 words centred on *position* for use as a highlight excerpt."""
    words = text.split()
    start = max(0, position - radius)
    end = min(len(words), position + radius)
    return " ".join(words[start:end])
