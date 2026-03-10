"""API endpoint tests using TestClient with mocked DB and suggestions."""

from unittest.mock import patch

import pytest

from app.schemas import Suggestion


class TestHealthAndRoot:
    """GET /health and GET /."""

    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_root_returns_html_or_message(self, client):
        r = client.get("/")
        assert r.status_code == 200
        if "text/html" in r.headers.get("content-type", ""):
            assert "html" in r.text.lower() or r.text.strip().startswith("<!")
        else:
            assert "message" in r.json() or "path" in r.json()


class TestSuggestionsEndpoint:
    """POST /suggestions with mocked get_suggestions_for_entry."""

    def test_returns_ranked_suggestions_and_low_confidence(self, client, sample_time_entry):
        stub_suggestions = [
            Suggestion(
                client_id="cli_001",
                matter_id="mat_001",
                client_name="Acme Corp",
                matter_name="Securities Matter",
                score=0.82,
                rationale="Suggested because the narrative is highly similar to this matter.",
            ),
        ]
        with patch("app.main.get_suggestions_for_entry", return_value=(stub_suggestions, False)):
            r = client.post("/suggestions", json=sample_time_entry)
        assert r.status_code == 200
        data = r.json()
        assert "suggestions" in data
        assert "low_confidence" in data
        assert data["low_confidence"] is False
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["client_name"] == "Acme Corp"
        assert data["suggestions"][0]["matter_name"] == "Securities Matter"
        assert data["suggestions"][0]["score"] == 0.82
        assert "rationale" in data["suggestions"][0]

    def test_low_confidence_true_when_flag_set(self, client, sample_time_entry):
        with patch("app.main.get_suggestions_for_entry", return_value=([], True)):
            r = client.post("/suggestions", json=sample_time_entry)
        assert r.status_code == 200
        assert r.json()["low_confidence"] is True
        assert r.json()["suggestions"] == []

    def test_validation_error_on_invalid_payload(self, client):
        r = client.post("/suggestions", json={"narrative": "only this"})
        assert r.status_code == 422


class TestFeedbackEndpoint:
    """POST /feedback with mocked record_feedback."""

    def test_accepts_valid_feedback_returns_201(self, client, sample_feedback_request):
        with patch("app.main.record_feedback", return_value=42):
            r = client.post("/feedback", json=sample_feedback_request)
        assert r.status_code == 201
        data = r.json()
        assert data["id"] == 42
        assert data["status"] == "recorded"

    def test_rejected_action_valid(self, client, sample_feedback_request):
        sample_feedback_request["action"] = "rejected"
        with patch("app.main.record_feedback", return_value=1):
            r = client.post("/feedback", json=sample_feedback_request)
        assert r.status_code == 201

    def test_invalid_action_returns_422(self, client, sample_feedback_request):
        sample_feedback_request["action"] = "invalid"
        r = client.post("/feedback", json=sample_feedback_request)
        assert r.status_code == 422
