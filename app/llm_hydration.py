"""
Async LLM rationale hydration.

We return suggestions immediately (template rationale) and populate LLM rationales
in the background. The UI polls a lightweight endpoint to fetch hydrated results.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import os
import logging

logger = logging.getLogger(__name__)

Key = Tuple[str, str]  # (user_id, entry_id)


@dataclass
class HydrationResult:
    status: str  # pending|ready|error
    created_at: float
    updated_at: float
    error: Optional[str]
    rationales: Dict[Tuple[str, str], str]  # (client_id, matter_id) -> llm_rationale


_LOCK = threading.Lock()
_STORE: Dict[Key, HydrationResult] = {}

# Simple TTL to avoid unbounded memory growth
TTL_S = 60.0 * 10.0


def _now() -> float:
    return time.time()


def _gc() -> None:
    cutoff = _now() - TTL_S
    with _LOCK:
        keys = [k for k, v in _STORE.items() if v.updated_at < cutoff]
        for k in keys:
            _STORE.pop(k, None)


def init_job(user_id: str, entry_id: str) -> None:
    _gc()
    key = (user_id, entry_id)
    with _LOCK:
        _STORE[key] = HydrationResult(
            status="pending",
            created_at=_now(),
            updated_at=_now(),
            error=None,
            rationales={},
        )
    if os.getenv("OLLAMA_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
        logger.info("LLM hydration job created for user_id=%s entry_id=%s", user_id, entry_id)


def set_ready(user_id: str, entry_id: str, mapping: Dict[Tuple[str, str], str]) -> None:
    key = (user_id, entry_id)
    with _LOCK:
        cur = _STORE.get(key)
        if cur is None:
            cur = HydrationResult(status="pending", created_at=_now(), updated_at=_now(), error=None, rationales={})
        cur.status = "ready"
        cur.updated_at = _now()
        cur.error = None
        cur.rationales = dict(mapping)
        _STORE[key] = cur


def set_error(user_id: str, entry_id: str, error: str) -> None:
    key = (user_id, entry_id)
    with _LOCK:
        cur = _STORE.get(key)
        if cur is None:
            cur = HydrationResult(status="pending", created_at=_now(), updated_at=_now(), error=None, rationales={})
        cur.status = "error"
        cur.updated_at = _now()
        cur.error = error[:500]
        _STORE[key] = cur


def get_status(user_id: str, entry_id: str) -> Optional[HydrationResult]:
    _gc()
    key = (user_id, entry_id)
    with _LOCK:
        return _STORE.get(key)


def list_recent_keys(limit: int = 10) -> List[Key]:
    """Debug helper: return up to N most-recently-updated keys."""
    with _LOCK:
        items = sorted(_STORE.items(), key=lambda kv: kv[1].updated_at, reverse=True)
    return [k for k, _v in items[:limit]]

