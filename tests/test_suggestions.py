"""Unit tests for suggestions module (rationale builder and get_suggestions with mocked DB)."""

from unittest.mock import patch, MagicMock
import pytest

from app.schemas import TimeEntry, Suggestion
from app.suggestions import _rationale, get_suggestions_for_entry
from datetime import date


class TestRationale:
    """Tests for _rationale() qualitative bands."""

    def test_high_semantic(self):
        r = _rationale(semantic=0.9, fts=0.0, affinity=0.5, recency=0.5)
        assert "highly similar" in r
        assert r.startswith("Suggested because")

    def test_medium_semantic(self):
        r = _rationale(semantic=0.6, fts=0.0, affinity=0.5, recency=0.5)
        assert "reasonable textual match" in r

    def test_low_semantic(self):
        r = _rationale(semantic=0.3, fts=0.0, affinity=0.5, recency=0.5)
        assert "weak textual match" in r

    def test_strong_fts(self):
        r = _rationale(semantic=0.5, fts=0.2, affinity=0.5, recency=0.5)
        # fts_norm = min(1, 0.2*5) = 1.0 -> strong keyword
        assert "strong keyword overlap" in r or "keyword" in r.lower()

    def test_some_fts(self):
        r = _rationale(semantic=0.5, fts=0.08, affinity=0.5, recency=0.5)
        # fts_norm = 0.4 -> some keywords
        assert "keyword" in r.lower() or "shares" in r.lower()

    def test_affinity_high(self):
        r = _rationale(semantic=0.5, fts=0.0, affinity=0.9, recency=0.5)
        assert "billed" in r or "frequently" in r or "worked" in r

    def test_affinity_neutral_no_extra(self):
        r = _rationale(semantic=0.5, fts=0.0, affinity=0.5, recency=0.5)
        assert "we do not yet have history" in r

    def test_recency_recent(self):
        r = _rationale(semantic=0.5, fts=0.0, affinity=0.5, recency=0.9)
        assert "recently" in r

    def test_recency_past(self):
        r = _rationale(semantic=0.5, fts=0.0, affinity=0.5, recency=0.4)
        assert "past" in r or "recent" in r

    def test_single_reason_format(self):
        r = _rationale(semantic=0.8, fts=0.0, affinity=0.5, recency=0.5)
        assert "Suggested because" in r
        assert ", and " not in r or r.count(", and ") == 1

    def test_fallback_when_no_reasons(self):
        # Edge case: all neutral / no bands triggered (should still get fallback from recency 0.5)
        r = _rationale(semantic=0.5, fts=0.0, affinity=0.5, recency=0.5)
        assert len(r) > 0
        assert "Suggested" in r


class TestGetSuggestionsForEntry:
    """Tests for get_suggestions_for_entry with mocked DB."""

    @pytest.fixture
    def entry(self):
        return TimeEntry(
            user_id="user_1",
            entry_id="entry_1",
            narrative="Drafted motion for summary judgment.",
            hours=1.0,
            entry_date=date(2025, 3, 1),
        )

    @patch("pgvector.psycopg.register_vector")
    @patch("app.suggestions.get_embedding")
    @patch("psycopg.connect")
    def test_returns_suggestions_and_low_confidence_flag(
        self, mock_connect, mock_get_embedding, _mock_register_vector, entry
    ):
        import numpy as np
        mock_get_embedding.return_value = np.zeros(384, dtype=np.float32)
        mock_cursor = MagicMock()
        # One row: client_id, matter_id, client_name, matter_name,
        # plus metadata and feedback counts (see SUGGESTIONS_QUERY SELECT).
        mock_cursor.fetchall.return_value = [
            (
                "cli_001",
                "mat_001",
                "Acme Corp",
                "Securities Matter",
                "Matter description",
                "Litigation",
                "Dispute",
                ["SEC", "disclosure"],
                0.7,
                0.1,
                0,
                0,
                None,
                0.5,
                0.5,
                1.0,
                0.45,  # below 0.55 -> low_confidence True
            ),
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_connect.return_value.__exit__.return_value = False

        suggestions, low_confidence = get_suggestions_for_entry(entry)
        assert len(suggestions) == 1
        assert suggestions[0].client_id == "cli_001"
        assert suggestions[0].matter_id == "mat_001"
        assert suggestions[0].client_name == "Acme Corp"
        assert suggestions[0].score == 0.45
        assert low_confidence is True

    @patch("pgvector.psycopg.register_vector")
    @patch("app.suggestions.get_embedding")
    @patch("psycopg.connect")
    def test_high_score_sets_low_confidence_false(
        self, mock_connect, mock_get_embedding, _mock_register_vector, entry
    ):
        import numpy as np
        mock_get_embedding.return_value = np.zeros(384, dtype=np.float32)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (
                "cli_001",
                "mat_001",
                "Acme Corp",
                "Securities Matter",
                "Matter description",
                "Litigation",
                "Dispute",
                ["SEC", "disclosure"],
                0.9,
                0.2,
                0,
                0,
                None,
                0.5,
                0.5,
                1.0,
                0.72,
            ),
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_connect.return_value.__exit__.return_value = False

        suggestions, low_confidence = get_suggestions_for_entry(entry)
        assert low_confidence is False
        assert suggestions[0].score == 0.72

    @patch("pgvector.psycopg.register_vector")
    @patch("app.suggestions.get_embedding")
    @patch("psycopg.connect")
    def test_empty_results(self, mock_connect, mock_get_embedding, _mock_register_vector, entry):
        import numpy as np
        mock_get_embedding.return_value = np.zeros(384, dtype=np.float32)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_connect.return_value.__exit__.return_value = False

        suggestions, low_confidence = get_suggestions_for_entry(entry)
        assert suggestions == []
        assert low_confidence is True
