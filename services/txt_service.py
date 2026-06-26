from pathlib import Path


def extract_txt_text(file_path: Path) -> str:
    """Read a TXT file using UTF-8 with a graceful fallback for legacy files."""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="latin-1")
