"""Unit tests for seed_matters (pure helpers and load_matters_json)."""

import json
import tempfile
from pathlib import Path

import pytest

from app.seed_matters import (
    _get,
    _get_list,
    _normalize_row,
    load_matters_json,
    get_default_matters_json_path,
)


class TestGet:
    """_get() helper."""

    def test_returns_first_present_key(self):
        row = {"a": 1, "b": 2}
        assert _get(row, "a", "A") == 1
        assert _get(row, "x", "a") == 1

    def test_returns_none_when_missing(self):
        row = {"a": 1}
        assert _get(row, "x", "y") is None

    def test_skips_none_value(self):
        row = {"a": None, "b": 2}
        assert _get(row, "a", "b") == 2


class TestGetList:
    """_get_list() helper."""

    def test_returns_list_from_snake(self):
        row = {"related_keywords": ["a", "b"]}
        assert _get_list(row, ("related_keywords", "RelatedKeywords")) == ["a", "b"]

    def test_returns_list_from_pascal(self):
        row = {"RelatedKeywords": ["x"]}
        assert _get_list(row, ("related_keywords", "RelatedKeywords")) == ["x"]

    def test_returns_empty_when_missing(self):
        row = {}
        assert _get_list(row, ("related_keywords", "RelatedKeywords")) == []

    def test_single_value_becomes_list(self):
        row = {"RelatedKeywords": "single"}
        assert _get_list(row, ("related_keywords", "RelatedKeywords")) == ["single"]


class TestNormalizeRow:
    """_normalize_row() mapping and validation."""

    def test_required_fields_from_pascal(self):
        row = {
            "ClientId": "c1",
            "ClientName": "Client One",
            "MatterId": "m1",
            "MatterName": "Matter One",
        }
        out = _normalize_row(row, 0)
        assert out["client_id"] == "c1"
        assert out["client_name"] == "Client One"
        assert out["matter_id"] == "m1"
        assert out["matter_name"] == "Matter One"
        assert out["matter_description"] is None
        assert out["status"] is None
        assert out["related_keywords"] == []
        assert out["involved_timekeepers"] == []

    def test_required_fields_from_snake(self):
        row = {
            "client_id": "c1",
            "client_name": "C1",
            "matter_id": "m1",
            "matter_name": "M1",
        }
        out = _normalize_row(row, 0)
        assert out["client_id"] == "c1"
        assert out["client_name"] == "C1"

    def test_missing_required_raises(self):
        row = {"ClientId": "c1"}  # missing others
        with pytest.raises(ValueError, match="missing required field"):
            _normalize_row(row, 0)

    def test_optional_fields_populated(self):
        row = {
            "ClientId": "c1",
            "ClientName": "C1",
            "MatterId": "m1",
            "MatterName": "M1",
            "MatterDescription": "Desc",
            "PracticeArea": "Corporate",
            "Status": "open",
            "RelatedKeywords": ["a", "b"],
            "InvolvedTimekeepers": ["tk_1"],
        }
        out = _normalize_row(row, 0)
        assert out["matter_description"] == "Desc"
        assert out["practice_area"] == "Corporate"
        assert out["status"] == "open"
        assert out["related_keywords"] == ["a", "b"]
        assert out["involved_timekeepers"] == ["tk_1"]


class TestLoadMattersJson:
    """load_matters_json() from file."""

    def test_load_valid_array(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                [
                    {
                        "ClientId": "c1",
                        "ClientName": "C1",
                        "MatterId": "m1",
                        "MatterName": "M1",
                    },
                ],
                f,
            )
            path = Path(f.name)
        try:
            rows = load_matters_json(path)
            assert len(rows) == 1
            assert rows[0]["client_id"] == "c1"
            assert rows[0]["client_name"] == "C1"
        finally:
            path.unlink()

    def test_not_array_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"not": "array"}, f)
            path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="array"):
                load_matters_json(path)
        finally:
            path.unlink()

    def test_skips_non_dict_elements(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                [
                    {"ClientId": "c1", "ClientName": "C1", "MatterId": "m1", "MatterName": "M1"},
                    "invalid",
                    None,
                ],
                f,
            )
            path = Path(f.name)
        try:
            rows = load_matters_json(path)
            assert len(rows) == 1
        finally:
            path.unlink()


class TestGetDefaultMattersJsonPath:
    """Default path is under project data/."""

    def test_returns_path_ending_with_matters_json(self):
        p = get_default_matters_json_path()
        assert p.name == "matters.json"
        assert "data" in p.parts
