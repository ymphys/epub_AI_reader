import pickle
from pathlib import Path
from typing import Any, BinaryIO

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry

_CLASS_REMAP = {
    ("__main__", "Book"): Book,
    ("__main__", "BookMetadata"): BookMetadata,
    ("__main__", "ChapterContent"): ChapterContent,
    ("__main__", "TOCEntry"): TOCEntry,
}


class Reader3Unpickler(pickle.Unpickler):
    """
    Custom unpickler to handle reader3 objects serialized when the module
    was executed as __main__ (e.g., running reader3.py directly).
    """

    def find_class(self, module: str, name: str) -> Any:
        key = (module, name)
        if key in _CLASS_REMAP:
            return _CLASS_REMAP[key]
        return super().find_class(module, name)


def load_book_pickle(path: Path):
    with open(path, "rb") as f:
        return Reader3Unpickler(f).load()
