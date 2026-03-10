import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# Project root (parent of app/)
APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_ROOT / "static"

from app.db import check_connection, record_feedback
from app.schemas import FeedbackRequest, SuggestionsResponse, TimeEntry
import os

from app.llm_hydration import get_status, init_job, list_recent_keys, set_error, set_ready
from app.seed_matters import run_seed_matters_background
from app.suggestions import generate_ollama_rationales_for_rows, get_suggestions_for_entry


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


@app.post("/feedback", status_code=201)
def post_feedback(feedback: FeedbackRequest):
    """Record accept or reject feedback for a suggestion."""
    feedback_id = record_feedback(
        user_id=feedback.user_id,
        entry_id=feedback.entry_id,
        client_id=feedback.client_id,
        matter_id=feedback.matter_id,
        action=feedback.action,
    )
    return {"id": feedback_id, "status": "recorded"}


@app.post("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(entry: TimeEntry, background: BackgroundTasks) -> SuggestionsResponse:
    """
    Accept a time entry and return a ranked list of client/matter suggestions.

    Uses narrative embedding (sentence-transformers), full-text search (tsvector),
    and user × matter feedback (affinity, recency, rejection penalty) in a single
    Postgres query; combines these into a single confidence score.
    """
    suggestions, low_confidence, rows = get_suggestions_for_entry(entry)

    # Kick off async LLM hydration (best-effort). UI will poll /suggestions/llm.
    init_job(entry.user_id, entry.entry_id)

    def _hydrate():
        try:
            mapping = generate_ollama_rationales_for_rows(entry, rows)
            set_ready(entry.user_id, entry.entry_id, mapping)
        except Exception as e:
            set_error(entry.user_id, entry.entry_id, str(e))

    background.add_task(_hydrate)
    return SuggestionsResponse(low_confidence=low_confidence, suggestions=suggestions)


@app.get("/suggestions/llm")
def get_llm_rationales(
    user_id: str = Query(...),
    entry_id: str = Query(...),
):
    """
    Poll LLM hydration results for a given (user_id, entry_id).
    """
    res = get_status(user_id, entry_id)
    if res is None:
        out = {"status": "missing", "rationales": []}
        if os.getenv("OLLAMA_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
            out["recent_keys"] = [{"user_id": u, "entry_id": e} for (u, e) in list_recent_keys()]
        return out
    return {
        "status": res.status,
        "error": res.error,
        "rationales": [
            {"client_id": cid, "matter_id": mid, "llm_rationale": txt}
            for (cid, mid), txt in res.rationales.items()
        ],
    }
