"""Unit tests for database module (get_database_url; optional integration for record_feedback)."""

import os
from unittest.mock import patch

import pytest

from app.db import get_database_url, ensure_feedback_table, record_feedback


class TestGetDatabaseUrl:
    """get_database_url() reads from environment."""

    def test_returns_env_value(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@localhost/db"}, clear=False):
            assert get_database_url() == "postgresql://u:p@localhost/db"

    def test_raises_when_unset(self):
        orig = os.environ.pop("DATABASE_URL", None)
        try:
            with pytest.raises(ValueError, match="DATABASE_URL"):
                get_database_url()
        finally:
            if orig is not None:
                os.environ["DATABASE_URL"] = orig


class TestEnsureFeedbackTableAndRecordFeedback:
    """Integration-style tests; skip if no DB. Pure unit test of record_feedback is not possible without DB."""

    @pytest.mark.skipif(
        "test_pointone" in os.getenv("DATABASE_URL", ""),
        reason="Use a real DATABASE_URL to run DB integration tests",
    )
    def test_ensure_feedback_table_does_not_raise(self):
        ensure_feedback_table()

    @pytest.mark.skipif(
        "test_pointone" in os.getenv("DATABASE_URL", ""),
        reason="Use a real DATABASE_URL to run DB integration tests",
    )
    def test_record_feedback_returns_id(self):
        fid = record_feedback(
            user_id="test_user",
            entry_id="test_entry",
            client_id="test_client",
            matter_id="test_matter",
            action="accepted",
        )
        assert isinstance(fid, int)
        assert fid >= 1
