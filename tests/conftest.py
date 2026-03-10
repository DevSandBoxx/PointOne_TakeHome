"""
Pytest configuration and shared fixtures.

Patches DB-dependent startup so the app can be tested without a real Postgres.
Set DATABASE_URL in env (or use a dummy) when using the client fixture.
"""

import os
from datetime import date
from unittest.mock import patch

import pytest

# Ensure DATABASE_URL is set before importing app (needed if any test triggers lifespan)
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_pointone")


@pytest.fixture(autouse=True)
def _patch_lifespan_deps():
    """Patch DB-dependent lifespan so TestClient can start without a real DB."""
    with patch("app.main.check_connection"), patch("app.main.run_seed_matters_background"):
        yield


@pytest.fixture
def client():
    """FastAPI test client. Lifespan is patched so no real DB is used at startup."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_time_entry():
    """Minimal valid time entry for API requests."""
    return {
        "user_id": "user_001",
        "entry_id": "entry_001",
        "narrative": "Drafted motion for summary judgment.",
        "hours": 2.5,
        "client_name": None,
        "matter_name": None,
        "entry_date": "2025-03-01",
    }


@pytest.fixture
def sample_feedback_request():
    """Valid feedback payload for POST /feedback."""
    return {
        "user_id": "user_001",
        "entry_id": "entry_001",
        "client_id": "cli_001",
        "matter_id": "mat_001",
        "action": "accepted",
    }


@pytest.fixture
def sample_suggestion():
    """A single Suggestion as returned by the suggestions API."""
    from app.schemas import Suggestion
    return Suggestion(
        client_id="cli_001",
        matter_id="mat_001",
        client_name="Acme Corporation",
        matter_name="Securities Investigation",
        score=0.85,
        rationale="Suggested because the narrative is highly similar to this matter.",
    )
