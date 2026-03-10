"""Unit tests for Ollama rationale parsing helpers."""

import pytest

from app.ollama_rationale import parse_rationales_json


def test_parse_rationales_plain_json():
    text = '{"rationales":[{"client_id":"c","matter_id":"m","rationale":"x"}]}'
    out = parse_rationales_json(text)
    assert out[("c", "m")] == "x"


def test_parse_rationales_fenced_json():
    text = "```json\n{\"rationales\":[{\"client_id\":\"c\",\"matter_id\":\"m\",\"rationale\":\"x\"}]}\n```\n"
    out = parse_rationales_json(text)
    assert out[("c", "m")] == "x"


def test_parse_rationales_with_extra_text_extracts_object():
    text = "here you go:\n```json\n{\"rationales\":[{\"client_id\":\"c\",\"matter_id\":\"m\",\"rationale\":\"x\"}]}\n```\nthanks"
    out = parse_rationales_json(text)
    assert out[("c", "m")] == "x"

def test_parse_rationales_accepts_rationales_object():
    text = '{"rationales":{"client_id":"c","matter_id":"m","rationale":"x"}}'
    out = parse_rationales_json(text)
    assert out[("c", "m")] == "x"


def test_parse_rationales_accepts_bare_list():
    text = '[{"client_id":"c","matter_id":"m","rationale":"x"}]'
    out = parse_rationales_json(text)
    assert out[("c", "m")] == "x"


def test_parse_rationales_accepts_single_object():
    text = '{"client_id":"c","matter_id":"m","rationale":"x"}'
    out = parse_rationales_json(text)
    assert out[("c", "m")] == "x"

def test_parse_rationales_accepts_results_alias():
    text = '{"results":[{"client_id":"c","matter_id":"m","rationale":"x"}]}'
    out = parse_rationales_json(text)
    assert out[("c", "m")] == "x"


def test_parse_rationales_missing_list_raises():
    with pytest.raises(ValueError):
        parse_rationales_json("{\"nope\": 1}")

