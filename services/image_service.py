from pathlib import Path

from services.ocr_service import extract_image_ocr_text


def extract_image_text(file_path: Path) -> str:
    """Extract text from supported image files with EasyOCR."""
    return extract_image_ocr_text(file_path)
