from pathlib import Path
from tempfile import TemporaryDirectory

import easyocr
from pdf2image import convert_from_path


_READER = None


def get_ocr_reader():
    """Create EasyOCR lazily because model loading is relatively expensive."""
    global _READER
    if _READER is None:
        _READER = easyocr.Reader(["en"], gpu=False)
    return _READER


def extract_image_ocr_text(file_path: Path) -> str:
    reader = get_ocr_reader()
    results = reader.readtext(str(file_path), detail=0, paragraph=True)
    return "\n".join(part for part in results if part.strip())


def extract_pdf_ocr_text(file_path: Path) -> str:
    """Convert scanned PDF pages to images and OCR each page."""
    page_text: list[str] = []

    with TemporaryDirectory() as temp_dir:
        try:
            pages = convert_from_path(file_path, output_folder=temp_dir, fmt="png")
        except Exception as exc:
            raise RuntimeError(
                "PDF OCR requires Poppler to be installed and available on PATH."
            ) from exc

        for page in pages:
            image_path = Path(temp_dir) / f"page-{len(page_text) + 1}.png"
            page.save(image_path, "PNG")
            text = extract_image_ocr_text(image_path)
            if text.strip():
                page_text.append(text)

    return "\n".join(page_text)
