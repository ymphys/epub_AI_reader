import os
import pickle
import json
from functools import lru_cache
from typing import Optional
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from deepseek_client import DeepSeekClient

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Where are the book folders located?
BOOKS_DIR = "."

# DeepSeek API Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
deepseek_client = None

if DEEPSEEK_API_KEY:
    deepseek_client = DeepSeekClient(DEEPSEEK_API_KEY)
    print("DeepSeek API client initialized successfully")
else:
    print("Warning: DEEPSEEK_API_KEY environment variable not set. AI features will be disabled.")

# Reading Progress Database
PROGRESS_DB_PATH = "reading_progress.db"

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

def get_reading_progress(book_id: str) -> Optional[int]:
    """Get reading progress for a book."""
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chapter_index FROM reading_progress WHERE book_id = ?
    ''', (book_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# Initialize database on startup
init_progress_db()

@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            if item.endswith("_data") and os.path.isdir(item):
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    # Get reading progress for this book
                    last_chapter = get_reading_progress(item)
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine),
                        "last_chapter": last_chapter
                    })

    return templates.TemplateResponse("library.html", {"request": request, "books": books})

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
        "spine_map_json": json.dumps(spine_map)
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

    img_path = os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)

    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)

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
    max_context_length = 2000
    if len(chapter_text) > max_context_length:
        chapter_text = chapter_text[:max_context_length] + "..."
    
    # Get AI response
    try:
        ai_response = deepseek_client.chat_with_context(
            user_message=user_message,
            book_context=chapter_text,
            chapter_title=chapter_title
        )
        
        return {
            "response": ai_response,
            "chapter_title": chapter_title
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
