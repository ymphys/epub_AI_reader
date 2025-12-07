import os
import json
import sqlite3
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from deepseek_client import DeepSeekClient
from reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from book_loader import load_book_pickle
from ai_defaults import (
    DEFAULT_AI_QUESTION,
    MAX_CONTEXT_LENGTH,
    DEFAULT_CACHE_FILENAME,
)
from library_paths import BOOK_DATA_DIR, READING_DB_PATH

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Where are the book folders located?
BOOKS_DIR = BOOK_DATA_DIR
CACHE_WRITE_LOCK = threading.Lock()

# DeepSeek API Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
deepseek_client = None

if DEEPSEEK_API_KEY:
    deepseek_client = DeepSeekClient(DEEPSEEK_API_KEY)
    print("DeepSeek API client initialized successfully")
else:
    print("Warning: DEEPSEEK_API_KEY environment variable not set. AI features will be disabled.")

# Reading Progress Database
PROGRESS_DB_PATH = str(READING_DB_PATH)

def init_progress_db():
    """Initialize the reading progress database."""
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reading_progress (
            book_id TEXT NOT NULL,
            chapter_index INTEGER NOT NULL,
            last_read TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (book_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS book_status (
            book_id TEXT PRIMARY KEY,
            is_done INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_reading_progress(book_id: str, chapter_index: int):
    """Save reading progress for a book."""
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO reading_progress (book_id, chapter_index, last_read)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (book_id, chapter_index))
    conn.commit()
    conn.close()

def get_reading_info(book_id: str) -> tuple[Optional[int], Optional[str]]:
    """Return chapter index and timestamp for a book."""
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chapter_index, last_read FROM reading_progress WHERE book_id = ?
    ''', (book_id,))
    result = cursor.fetchone()
    conn.close()
    if not result:
        return None, None
    return result[0], result[1]


def get_reading_progress(book_id: str) -> Optional[int]:
    chapter_index, _ = get_reading_info(book_id)
    return chapter_index


def set_book_done(book_id: str, done: bool):
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO book_status (book_id, is_done, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(book_id)
        DO UPDATE SET is_done=excluded.is_done, updated_at=CURRENT_TIMESTAMP
    ''', (book_id, 1 if done else 0))
    conn.commit()
    conn.close()


def is_book_done(book_id: str) -> bool:
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT is_done FROM book_status WHERE book_id = ?', (book_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

# Initialize database on startup
init_progress_db()


def _cache_path_for_book(book_id: str) -> Path:
    return Path(BOOKS_DIR) / book_id / DEFAULT_CACHE_FILENAME


@lru_cache(maxsize=50)
def load_default_ai_cache(book_id: str) -> Optional[Dict[str, Any]]:
    """
    Load cached default AI answers for a book if present.
    """
    cache_path = _cache_path_for_book(book_id)
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load AI cache for {book_id}: {e}")
        return None


def get_default_ai_answer(book_id: str, chapter_index: int) -> Optional[Dict[str, Any]]:
    cache = load_default_ai_cache(book_id)
    if not cache:
        return None

    answers = cache.get("answers", {})
    entry = answers.get(str(chapter_index))
    if not entry:
        return None
        
    # Skip if chapter is marked as filtered
    if entry.get("filtered"):
        return None

    return {
        "question": cache.get("prompt", DEFAULT_AI_QUESTION),
        "answer": entry.get("answer", ""),
        "chapter_title": entry.get("title"),
        "generated_at": entry.get("generated_at", cache.get("generated_at")),
    }


def is_chapter_filtered(book_id: str, chapter_index: int) -> bool:
    cache = load_default_ai_cache(book_id)
    if not cache:
        return False
    answers = cache.get("answers", {})
    entry = answers.get(str(chapter_index))
    if not entry:
        return False
    return bool(entry.get("filtered"))


def get_chapter_qa_history(book_id: str, chapter_index: int) -> List[Dict[str, Any]]:
    cache = load_default_ai_cache(book_id)
    if not cache:
        return []

    qa_logs = cache.get("qa_logs", {})
    return qa_logs.get(str(chapter_index), [])


def append_chat_history(book_id: str, chapter_index: int, chapter_title: str, question: str, answer: str) -> None:
    """
    Persist user Q&A pairs into the default cache file so they can be reviewed later.
    """
    cache_path = _cache_path_for_book(book_id)
    cache_data: Dict[str, Any] = {}

    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read cache for logging ({book_id}): {e}")
            cache_data = {}

    if not cache_data:
        cache_data = {
            "book_id": book_id,
            "prompt": DEFAULT_AI_QUESTION,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "answers": {},
        }

    cache_data.setdefault("book_id", book_id)
    cache_data.setdefault("prompt", DEFAULT_AI_QUESTION)
    cache_data.setdefault("answers", {})
    qa_logs = cache_data.setdefault("qa_logs", {})

    chapter_key = str(chapter_index)
    chapter_logs = qa_logs.setdefault(chapter_key, [])
    now_iso = datetime.utcnow().isoformat() + "Z"
    chapter_logs.append({
        "question": question,
        "answer": answer,
        "chapter_title": chapter_title,
        "asked_at": now_iso,
        "answered_at": datetime.utcnow().isoformat() + "Z",
    })

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with CACHE_WRITE_LOCK, open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        load_default_ai_cache.cache_clear()
    except Exception as e:
        print(f"Warning: Failed to append chat history for {book_id}: {e}")


BOOK_CACHE: Dict[str, Dict[str, Any]] = {}


def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cache is keyed by folder name + book.pkl mtime so new/updated books show up without restarting.
    """
    file_path = BOOKS_DIR / folder_name / "book.pkl"
    if not file_path.exists():
        BOOK_CACHE.pop(folder_name, None)
        return None

    try:
        mtime = file_path.stat().st_mtime
    except OSError:
        BOOK_CACHE.pop(folder_name, None)
        return None

    cached = BOOK_CACHE.get(folder_name)
    if cached and cached.get("mtime") == mtime:
        return cached.get("book")

    try:
        book = load_book_pickle(file_path)
        BOOK_CACHE[folder_name] = {"mtime": mtime, "book": book}
        return book
    except Exception as e:
        BOOK_CACHE.pop(folder_name, None)
        print(f"Error loading book {folder_name}: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    current_books = []
    completed_books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if BOOKS_DIR.exists():
        for folder in sorted(BOOKS_DIR.iterdir()):
            if folder.is_dir() and folder.name.endswith("_data"):
                # Try to load it to get the title
                book = load_book_cached(folder.name)
                if book:
                    last_chapter, last_read_time = get_reading_info(folder.name)
                    done = is_book_done(folder.name)
                    book_info = {
                        "id": folder.name,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine),
                        "last_chapter": last_chapter,
                        "last_read_time": last_read_time,
                        "is_done": done,
                    }
                    if done:
                        completed_books.append(book_info)
                    else:
                        current_books.append(book_info)

    current_books.sort(key=lambda book: book.get("last_read_time") or "", reverse=True)
    completed_books.sort(key=lambda book: book.get("last_read_time") or "", reverse=True)

    context = {
        "request": request,
        "current_books": current_books,
        "completed_books": completed_books,
    }
    return templates.TemplateResponse("library.html", context)

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(book_id: str):
    """Helper to just go to chapter 0."""
    return await read_chapter(book_id=book_id, chapter_index=0)

@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    # Save reading progress
    save_reading_progress(book_id, chapter_index)

    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx
    })

@app.get("/read-ai/{book_id}", response_class=HTMLResponse)
async def redirect_to_ai_reader(request: Request, book_id: str):
    """Redirect to AI reader, starting from last read position or chapter 0."""
    # Get last reading progress
    last_chapter = get_reading_progress(book_id)
    chapter_index = last_chapter if last_chapter is not None else 0
    
    # Save progress (in case we're starting from beginning)
    save_reading_progress(book_id, chapter_index)
    
    return await read_chapter_with_ai(request=request, book_id=book_id, chapter_index=chapter_index)

@app.get("/read-ai/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter_with_ai(request: Request, book_id: str, chapter_index: int):
    """The AI-enhanced reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    # Create spine map for JavaScript
    spine_map = {}
    for ch in book.spine:
        spine_map[ch.href] = ch.order

    # Save reading progress
    save_reading_progress(book_id, chapter_index)

    return templates.TemplateResponse("reader_with_ai.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx,
        "spine_map_json": json.dumps(spine_map),
        "default_ai_data": get_default_ai_answer(book_id, chapter_index),
        "default_ai_question": DEFAULT_AI_QUESTION,
        "chapter_is_filtered": is_chapter_filtered(book_id, chapter_index),
        "qa_history": get_chapter_qa_history(book_id, chapter_index),
    })

@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = BOOKS_DIR / safe_book_id / "images" / safe_image_name

    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(str(img_path))

@app.get("/read-ai/{book_id}/images/{image_name}")
async def serve_image_ai(book_id: str, image_name: str):
    """
    Serves images specifically for a book in AI reader.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read-ai/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = BOOKS_DIR / safe_book_id / "images" / safe_image_name

    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(str(img_path))

@app.post("/api/chat/{book_id}/{chapter_index}")
async def chat_with_ai(book_id: str, chapter_index: int, request: Request):
    """
    Chat with DeepSeek AI about the current chapter content.
    """
    if not deepseek_client:
        raise HTTPException(status_code=503, detail="AI service not available. Please set DEEPSEEK_API_KEY environment variable.")
    
    # Load the book
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Get request data
    data = await request.json()
    user_message = data.get("message", "")
    
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    # Get current chapter context
    current_chapter = book.spine[chapter_index]
    chapter_title = current_chapter.title
    chapter_text = current_chapter.text
    
    # Limit context length to avoid token limits
    if len(chapter_text) > MAX_CONTEXT_LENGTH:
        chapter_text = chapter_text[:MAX_CONTEXT_LENGTH] + "..."
    
    # Get AI response
    try:
        ai_response = deepseek_client.chat_with_context(
            user_message=user_message,
            book_context=chapter_text,
            chapter_title=chapter_title
        )

        try:
            append_chat_history(
                book_id=book_id,
                chapter_index=chapter_index,
                chapter_title=chapter_title,
                question=user_message,
                answer=ai_response,
            )
        except Exception as log_error:
            print(f"Warning: Unable to log chat history for {book_id}: {log_error}")
        
        return {
            "response": ai_response,
            "chapter_title": chapter_title
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")


@app.post("/api/book-status/{book_id}")
async def update_book_status(book_id: str, request: Request):
    """
    Toggle whether a book is considered "done reading".
    """
    data = await request.json()
    done_flag = bool(data.get("done"))
    set_book_done(book_id, done_flag)
    return {"book_id": book_id, "done": done_flag}

if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
