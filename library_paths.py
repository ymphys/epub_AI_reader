import os
from pathlib import Path
from typing import Iterable


def _normalize(path_value) -> Path:
    if isinstance(path_value, Path):
        return path_value.expanduser()
    return Path(path_value).expanduser()


LIBRARY_ROOT = _normalize(os.getenv("LIBRARY_ROOT", "library"))
EPUB_LIBRARY_DIR = _normalize(os.getenv("LIBRARY_EPUB_DIR", LIBRARY_ROOT / "epubs"))
BOOK_DATA_DIR = _normalize(os.getenv("LIBRARY_DATA_DIR", LIBRARY_ROOT / "data"))
READING_DB_PATH = _normalize(os.getenv("READING_PROGRESS_DB", BOOK_DATA_DIR / "reading_progress.db"))

# Ensure base folders exist so other modules can rely on them.
for directory in (EPUB_LIBRARY_DIR, BOOK_DATA_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def candidate_book_dirs(identifier: str) -> Iterable[Path]:
    """
    Yield likely locations for a processed *_data folder based on the identifier supplied.
    """
    direct_path = Path(identifier)
    yield direct_path
    if direct_path.exists():
        return

    yield BOOK_DATA_DIR / identifier
    if identifier.endswith("_data"):
        return
    yield BOOK_DATA_DIR / f"{identifier}_data"
