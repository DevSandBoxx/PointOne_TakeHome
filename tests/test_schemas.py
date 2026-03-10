"""Unit tests for Pydantic schemas (validation and serialization)."""

import pytest
from datetime import date
from pydantic import ValidationError

from app.schemas import (
    TimeEntry,
    Suggestion,
    SuggestionsResponse,
    FeedbackRequest,
)


class TestTimeEntry:
    """TimeEntry model validation."""

    def test_valid_minimal(self):
        data = {
            "user_id": "u1",
            "entry_id": "e1",
            "narrative": "Work on contract.",
            "hours": 1.0,
            "entry_date": "2025-01-15",
        }
        entry = TimeEntry(**data)
        assert entry.user_id == "u1"
        assert entry.entry_id == "e1"
        assert entry.narrative == "Work on contract."
        assert entry.hours == 1.0
        assert entry.entry_date == date(2025, 1, 15)
        assert entry.client_name is None
        assert entry.matter_name is None

    def test_valid_with_optional(self):
        data = {
            "user_id": "u1",
            "entry_id": "e1",
            "narrative": "Drafted memo.",
            "hours": 0.5,
            "client_name": "Acme Corp",
            "matter_name": "Matter X",
            "entry_date": "2025-03-01",
        }
        entry = TimeEntry(**data)
        assert entry.client_name == "Acme Corp"
        assert entry.matter_name == "Matter X"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            TimeEntry(
                user_id="u1",
                entry_id="e1",
                narrative="x",
                # missing hours and entry_date
            )

    def test_hours_negative_raises(self):
        with pytest.raises(ValidationError):
            TimeEntry(
                user_id="u1",
                entry_id="e1",
                narrative="x",
                hours=-1.0,
                entry_date="2025-01-01",
            )


class TestSuggestion:
    """Suggestion model validation."""

    def test_valid(self):
        s = Suggestion(
            client_id="c1",
            matter_id="m1",
            client_name="Client A",
            matter_name="Matter B",
            score=0.75,
            semantic_score=0.7,
            keyword_score=0.2,
            affinity=0.5,
            recency=0.5,
            rationale="Good match.",
            llm_status="pending",
        )
        assert s.client_id == "c1"
        assert s.matter_id == "m1"
        assert s.score == 0.75
        assert s.rationale == "Good match."

    def test_score_bounds(self):
        Suggestion(
            client_id="c1",
            matter_id="m1",
            client_name="A",
            matter_name="B",
            score=0.0,
            semantic_score=0.0,
            keyword_score=0.0,
            affinity=0.5,
            recency=0.5,
            llm_status="disabled",
        )
        Suggestion(
            client_id="c1",
            matter_id="m1",
            client_name="A",
            matter_name="B",
            score=1.0,
            semantic_score=1.0,
            keyword_score=1.0,
            affinity=1.0,
            recency=1.0,
            llm_status="disabled",
        )

    def test_score_below_zero_raises(self):
        with pytest.raises(ValidationError):
            Suggestion(
                client_id="c1",
                matter_id="m1",
                client_name="A",
                matter_name="B",
                score=-0.1,
                semantic_score=0.0,
                keyword_score=0.0,
                affinity=0.5,
                recency=0.5,
                llm_status="disabled",
            )

    def test_score_above_one_raises(self):
        with pytest.raises(ValidationError):
            Suggestion(
                client_id="c1",
                matter_id="m1",
                client_name="A",
                matter_name="B",
                score=1.1,
                semantic_score=0.0,
                keyword_score=0.0,
                affinity=0.5,
                recency=0.5,
                llm_status="disabled",
            )


class TestSuggestionsResponse:
    """SuggestionsResponse model."""

    def test_valid_empty_suggestions(self):
        r = SuggestionsResponse(low_confidence=True, suggestions=[])
        assert r.low_confidence is True
        assert r.suggestions == []

    def test_valid_with_suggestions(self):
        suggestions = [
            Suggestion(
                client_id="c1",
                matter_id="m1",
                client_name="C1",
                matter_name="M1",
                score=0.8,
                semantic_score=0.7,
                keyword_score=0.2,
                affinity=0.5,
                recency=0.5,
                llm_status="pending",
            ),
        ]
        r = SuggestionsResponse(low_confidence=False, suggestions=suggestions)
        assert r.low_confidence is False
        assert len(r.suggestions) == 1
        assert r.suggestions[0].client_name == "C1"


class TestFeedbackRequest:
    """FeedbackRequest model."""

    def test_valid_accepted(self):
        f = FeedbackRequest(
            user_id="u1",
            entry_id="e1",
            client_id="c1",
            matter_id="m1",
            action="accepted",
        )
        assert f.action == "accepted"

    def test_valid_rejected(self):
        f = FeedbackRequest(
            user_id="u1",
            entry_id="e1",
            client_id="c1",
            matter_id="m1",
            action="rejected",
        )
        assert f.action == "rejected"

    def test_invalid_action_raises(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(
                user_id="u1",
                entry_id="e1",
                client_id="c1",
                matter_id="m1",
                action="maybe",
            )
