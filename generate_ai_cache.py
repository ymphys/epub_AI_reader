import argparse
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from deepseek_client import DeepSeekClient
from ai_defaults import (
    DEFAULT_AI_QUESTION,
    MAX_CONTEXT_LENGTH,
    DEFAULT_CACHE_FILENAME,
)
from book_loader import load_book_pickle
from library_paths import BOOK_DATA_DIR, candidate_book_dirs


def load_book(book_dir: Path):
    book_path = book_dir / "book.pkl"
    if not book_path.exists():
        raise FileNotFoundError(f"book.pkl not found in {book_dir}")

    return load_book_pickle(book_path)


def resolve_book_dir(arg: str) -> Path:
    for candidate in candidate_book_dirs(arg):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Unable to find processed folder for '{arg}'. Expected under {BOOK_DATA_DIR}.")


def truncate_context(text: str) -> str:
    if len(text) <= MAX_CONTEXT_LENGTH:
        return text
    return text[:MAX_CONTEXT_LENGTH] + "..."


MIN_WORD_COUNT = 100

TITLE_SKIP_KEYWORDS = [
    ("cover", "title_contains_cover"),
    ("封面", "title_contains_cover"),
    ("back cover", "title_contains_back_cover"),
    ("references", "title_contains_references"),
    ("参考文献", "title_contains_references"),
    ("bibliography", "title_contains_bibliography"),
    ("参考书目", "title_contains_bibliography"),
    ("acknowledgements", "title_contains_acknowledgements"),
    ("acknowledgments", "title_contains_acknowledgements"),
    ("致谢", "title_contains_acknowledgements"),
    ("table of contents", "title_contains_contents"),
    ("contents", "title_contains_contents"),
    ("目录", "title_contains_contents"),
    ("content", "title_contains_contents"),
    ("thank you", "title_contains_thank_you"),
    ("致谢词", "title_contains_thank_you"),
]


def get_filter_reason(chapter_title: str, chapter_text: str) -> Optional[str]:
    """Return why a chapter would be filtered, or None if it should be kept."""
    text = chapter_text or ""
    stripped_text = text.strip()
    title = (chapter_title or "").strip()

    if not stripped_text:
        return "empty_text"

    title_lower = title.lower()

    for keyword, reason in TITLE_SKIP_KEYWORDS:
        if keyword in title_lower:
            return reason

    word_count = len(stripped_text.split())
    if word_count < MIN_WORD_COUNT:
        return f"too_short ({word_count} words)"

    return None


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
    filter_stats: Counter[str] = Counter()

    for idx, chapter in enumerate(book.spine):
        key = str(idx)
        if key in answers and answers[key].get("answer"):
            print(f" - Chapter {idx + 1}/{len(book.spine)} already cached; skipping.")
            continue

        chapter_title = getattr(chapter, "title", f"Chapter {idx}")
        chapter_text = getattr(chapter, "text", "")

        filter_reason = get_filter_reason(chapter_title, chapter_text)
        if filter_reason:
            print(
                f" - Skipping chapter {idx + 1}/{len(book.spine)}: {chapter_title} "
                f"(filtered: {filter_reason})"
            )
            answers[key] = {
                "title": chapter_title,
                "href": getattr(chapter, "href", ""),
                "filtered": True,
                "filter_reason": filter_reason,
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }
            filter_stats[filter_reason] += 1
            continue

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

    if filter_stats:
        print("Filter summary:")
        for reason, count in filter_stats.items():
            print(f"   {count} chapter(s) filtered due to {reason}")

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

    for book_arg in args.book_dirs:
        book_dir = resolve_book_dir(book_arg)
        build_cache_for_book(book_dir, client, force=args.force)


if __name__ == "__main__":
    main()
