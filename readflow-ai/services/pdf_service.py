from pathlib import Path

import pdfplumber

from services.ocr_service import extract_pdf_ocr_text


def extract_pdf_text(file_path: Path) -> str:
    """Extract selectable PDF text, falling back to OCR for scanned PDFs."""
    parts: list[str] = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text)

    text = "\n".join(parts).strip()
    if text:
        return text

    return extract_pdf_ocr_text(file_path)
