from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from app.db import check_connection
from app.schemas import SuggestionsResponse, TimeEntry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure DB connection and pgvector are available before accepting requests."""
    check_connection()
    yield


app = FastAPI(
    title="Client/Matter Suggestion API",
    description="Returns ranked client/matter suggestions for time entries.",
    version="0.1.0",
    lifespan=lifespan,
)

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(entry: TimeEntry) -> SuggestionsResponse:
    """
    Accept a time entry and return a ranked list of client/matter suggestions.

    Each suggestion includes client name, matter name, a confidence score,
    and an optional rationale.
    """
    # Phase 1: no logic yet — return empty ranked list
    return SuggestionsResponse(suggestions=[])
