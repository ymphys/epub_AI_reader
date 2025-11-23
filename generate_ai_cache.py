import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from deepseek_client import DeepSeekClient
from ai_defaults import (
    DEFAULT_AI_QUESTION,
    MAX_CONTEXT_LENGTH,
    DEFAULT_CACHE_FILENAME,
)
from book_loader import load_book_pickle


def load_book(book_dir: Path):
    book_path = book_dir / "book.pkl"
    if not book_path.exists():
        raise FileNotFoundError(f"book.pkl not found in {book_dir}")

    return load_book_pickle(book_path)


def truncate_context(text: str) -> str:
    if len(text) <= MAX_CONTEXT_LENGTH:
        return text
    return text[:MAX_CONTEXT_LENGTH] + "..."


def build_cache_for_book(book_dir: Path, client: DeepSeekClient, force: bool) -> None:
    print(f"\nPreparing default AI cache for {book_dir.name}")
    cache_path = book_dir / DEFAULT_CACHE_FILENAME

    existing_data: Dict[str, Any] = {}
    if cache_path.exists() and not force:
        with open(cache_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
        print(f"Found existing cache with {len(existing_data.get('answers', {}))} entries. Resuming where possible.")
    elif cache_path.exists() and force:
        print("Force flag detected; existing cache will be replaced.")

    book = load_book(book_dir)
    answers = {} if force else existing_data.get("answers", {})

    for idx, chapter in enumerate(book.spine):
        key = str(idx)
        if key in answers and answers[key].get("answer"):
            print(f" - Chapter {idx + 1}/{len(book.spine)} already cached; skipping.")
            continue

        chapter_title = getattr(chapter, "title", f"Chapter {idx}")
        chapter_text = getattr(chapter, "text", "")
        context = truncate_context(chapter_text)

        print(f" - Caching chapter {idx + 1}/{len(book.spine)}: {chapter_title}")
        ai_response = client.chat_with_context(
            user_message=DEFAULT_AI_QUESTION,
            book_context=context,
            chapter_title=chapter_title,
        )

        answers[key] = {
            "title": chapter_title,
            "href": getattr(chapter, "href", ""),
            "answer": ai_response,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    cache_payload = {
        "book_id": book_dir.name,
        "prompt": DEFAULT_AI_QUESTION,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "answers": answers,
    }

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, ensure_ascii=False, indent=2)

    print(f"Done. Cached answers saved to {cache_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate cached DeepSeek answers for the default question."
    )
    parser.add_argument(
        "book_dirs",
        nargs="+",
        help="One or more processed EPUB folders (e.g., my_book_data)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute all chapters even if a cache already exists.",
    )
    args = parser.parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is required to generate the cache.")

    client = DeepSeekClient(api_key)

    for book_dir in args.book_dirs:
        build_cache_for_book(Path(book_dir), client, force=args.force)


if __name__ == "__main__":
    main()
