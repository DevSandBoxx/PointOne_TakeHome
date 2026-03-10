import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# Project root (parent of app/)
APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_ROOT / "static"

from app.db import check_connection
from app.schemas import SuggestionsResponse, TimeEntry
from app.seed_matters import run_seed_matters_background
from app.suggestions import get_suggestions_for_entry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure DB connection, pgvector, and feedback table; then seed matters in background."""
    check_connection()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run_seed_matters_background)
    yield


app = FastAPI(
    title="Client/Matter Suggestion API",
    description="Returns ranked client/matter suggestions for time entries.",
    version="0.1.0",
    lifespan=lifespan,
)

# Static assets (CSS, JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_ui():
    """Serve the time entry / classification suggestions UI."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return {"message": "UI not found", "path": str(index_path)}
    return FileResponse(index_path)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(entry: TimeEntry) -> SuggestionsResponse:
    """
    Accept a time entry and return a ranked list of client/matter suggestions.

    Uses narrative embedding (sentence-transformers) and full-text search (tsvector)
    in a single Postgres query; combines semantic and keyword scores.
    """
    suggestions = get_suggestions_for_entry(entry.narrative)
    return SuggestionsResponse(suggestions=suggestions)
