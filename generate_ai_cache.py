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


def should_skip_chapter(chapter_title: str, chapter_text: str) -> bool:
    """Check if chapter should be skipped based on content criteria."""
    
    # Check if text is blank or only whitespace
    if not chapter_text or not chapter_text.strip():
        return True
    
    # Convert to lowercase for case-insensitive matching
    title_lower = chapter_title.lower()
    text_lower = chapter_text.lower()
    
    # Skip keywords in title
    skip_keywords = [
        "cover", "back cover", "references", "bibliography",
        "thank you", "acknowledgements", "acknowledgments",
        "contents", "table of contents", "index", "preface",
        "foreword", "introduction", "appendix"
    ]
    
    for keyword in skip_keywords:
        if keyword in title_lower:
            return True
    
    # Skip if content is too short (less than 100 words)
    word_count = len(chapter_text.split())
    if word_count < 100:
        return True
    
    return False


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
        
        # Skip chapters that meet the filtering criteria, but mark them in cache
        if should_skip_chapter(chapter_title, chapter_text):
            print(f" - Skipping chapter {idx + 1}/{len(book.spine)}: {chapter_title} (filtered)")
            # Create an entry marked as filtered
            answers[key] = {
                "title": chapter_title,
                "href": getattr(chapter, "href", ""),
                "filtered": True,
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }
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
