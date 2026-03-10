"""
Ollama integration for rationale generation.

This is intentionally optional and best-effort:
- If disabled (default), callers should use template rationales.
- If enabled but Ollama is unreachable / returns invalid output, we fall back.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class OllamaConfig:
    enabled: bool
    base_url: str
    model: str
    timeout_s: float


def get_ollama_config() -> OllamaConfig:
    enabled = os.getenv("OLLAMA_RATIONALE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    base_url = (os.getenv("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL") or "llama3.1"
    try:
        timeout_s = float(os.getenv("OLLAMA_TIMEOUT_S") or "4.0")
    except ValueError:
        timeout_s = 4.0
    return OllamaConfig(enabled=enabled, base_url=base_url, model=model, timeout_s=timeout_s)


def _post_json(url: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def ollama_generate(*, base_url: str, model: str, prompt: str, timeout_s: float) -> str:
    """
    Call Ollama's generate endpoint and return the response text.

    Uses `stream=false` so this is a single request/response.
    """
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        # Keep outputs more deterministic / less chatty.
        "options": {"temperature": 0.2},
    }

    # When supported, this forces JSON-only output at the server/model layer.
    # If unsupported by a model, Ollama may ignore it or error; caller will fallback.
    if os.getenv("OLLAMA_FORCE_JSON", "").strip().lower() in {"1", "true", "yes", "on"}:
        payload["format"] = "json"

    out = _post_json(
        f"{base_url}/api/generate",
        payload,
        timeout_s=timeout_s,
    )
    text = out.get("response")
    if not isinstance(text, str):
        raise ValueError("Ollama response missing 'response' string")
    return text


def build_batch_prompt(
    *,
    user_id: str,
    entry_id: str,
    narrative: str,
    candidates: Iterable[dict[str, Any]],
) -> str:
    """
    Create a single prompt to generate rationales for multiple candidates.

    "Option A" writing style: text-first, personalization-second.
    """
    # Keep JSON input compact; Ollama models behave better with structured prompts.
    candidates_list = list(candidates)
    payload = {
        "user_id": user_id,
        "entry_id": entry_id,
        "narrative": narrative,
        "candidates": candidates_list,
    }
    return (
        "You are generating rationales for ranked client/matter suggestions in a law firm.\n"
        "Write in Option A style: mention text match (semantic/keywords) first, then personalization (affinity/recency) second.\n"
        "Return ONLY valid JSON (no markdown, no code fences) with this exact shape:\n"
        "{\n"
        '  "rationales": [\n'
        '    {"client_id": "...", "matter_id": "...", "rationale": "1–2 sentences."}\n'
        "  ]\n"
        "}\n"
        "Constraints:\n"
        "- 1–2 sentences per candidate; <= 45 words.\n"
        "- Do not invent facts outside the provided fields.\n"
        "- The top-level 'narrative' is the USER'S time entry narrative. Matter titles/descriptions are separate fields.\n"
        "- Never quote a phrase as being from the narrative unless it appears in narrative_terms.\n"
        "- When referencing the narrative, say 'the narrative includes terms like X/Y/Z' using narrative_terms (not the matter title).\n"
        "- Define 'no prior history' as: fewer than 3 feedback events (accepted/rejected) by this user for this matter.\n"
        "- If keyword_overlap is non-empty, mention 1–3 overlapping terms to justify the keyword match.\n"
        "- Include brief score references using the provided numeric signals as percentages (rounded), e.g. 'Semantic ~72%, Keywords ~18%'.\n"
        "- Respect confidence_band:\n"
        "  - If confidence_band == 'low', explicitly say this is a low-confidence/uncertain suggestion and avoid phrases like 'strong match'.\n"
        "  - If confidence_band == 'medium', use hedged language like 'possible match' or 'reasonable match'.\n"
        "  - If confidence_band == 'high', you may say 'strong match'.\n"
        "- Do not just restate the client/matter title. Explain why the narrative aligns with the matter_description/keywords and why that leads to a higher rank.\n"
        "- Do not claim the matter is truly 'involved in' something; instead say it 'matches' based on the narrative and metadata.\n"
        "\n"
        "INPUT JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
    )


def parse_rationales_json(text: str) -> dict[tuple[str, str], str]:
    """
    Parse the model output into a mapping (client_id, matter_id) -> rationale.
    """
    raw = text.strip()

    if not raw:
        raise ValueError("Empty Ollama response text")

    # Many models still wrap JSON in fenced code blocks despite instructions, e.g.:
    # ```json
    # { ... }
    # ```
    if "```" in raw:
        # Drop the fence markers while keeping inner content.
        raw = raw.replace("```json", "").replace("```JSON", "").replace("```", "").strip()

    # If there's extra text, try to extract the largest JSON object substring.
    # This is a best-effort heuristic to avoid falling back when the model is "nearly" correct.
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1].strip()

    if not raw:
        raise ValueError("Ollama response contained no JSON object")

    obj = json.loads(raw)

    # Accept a few common output shapes:
    # 1) {"rationales": [ {...}, ... ]}  (preferred)
    # 2) {"rationales": {...}}          (single object)
    # 3) [ {...}, ... ]                 (bare list)
    # 4) {"client_id":..., "matter_id":..., "rationale":...} (single object)
    items: Any = None
    if isinstance(obj, dict):
        items = obj.get("rationales")
        if items is None:
            # Some models return a similar envelope like {"results":[...]}.
            items = obj.get("results")
        if items is None and all(k in obj for k in ("client_id", "matter_id", "rationale")):
            items = [obj]
    elif isinstance(obj, list):
        items = obj

    if isinstance(items, dict):
        items = [items]

    if not isinstance(items, list):
        keys = list(obj.keys()) if isinstance(obj, dict) else type(obj).__name__
        raise ValueError(f"Invalid Ollama rationale payload: missing 'rationales' list (got keys/type: {keys})")
    out: dict[tuple[str, str], str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("client_id")
        mid = it.get("matter_id")
        rat = it.get("rationale")
        if isinstance(cid, str) and isinstance(mid, str) and isinstance(rat, str) and rat.strip():
            out[(cid, mid)] = rat.strip()
    return out

