"""Unit tests for the embedding module."""

import numpy as np
import pytest

from app.embedding import get_embedding


class TestGetEmbedding:
    """Tests for get_embedding()."""

    def test_returns_ndarray(self):
        vec = get_embedding("Drafted a contract for the merger.")
        assert isinstance(vec, np.ndarray)
        assert vec.dtype in (np.float32, np.float64)

    def test_dimension_matches_minilm(self):
        # all-MiniLM-L6-v2 has dimension 384
        vec = get_embedding("short text")
        assert vec.ndim == 1
        assert vec.shape[0] == 384

    def test_empty_string_uses_space(self):
        """Empty or whitespace input should not raise; implementation uses ' '."""
        vec = get_embedding("")
        assert vec is not None
        assert len(vec) == 384
        vec2 = get_embedding("   ")
        assert vec2 is not None
        assert len(vec2) == 384

    def test_deterministic_for_same_input(self):
        text = "Review of SEC filing."
        a = get_embedding(text)
        b = get_embedding(text)
        np.testing.assert_array_almost_equal(a, b)

    def test_different_inputs_differ(self):
        a = get_embedding("Contract review")
        b = get_embedding("Litigation motion")
        assert not np.allclose(a, b)
