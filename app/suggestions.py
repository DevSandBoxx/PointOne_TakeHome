"""
Phase 2: ranked client/matter suggestions via one Postgres query (semantic + FTS)
with additive personalization features (affinity, recency, rejection penalty).

See docs/SUGGESTIONS_SCORING.md for what the base query returns and how scores
are combined; this module extends that with user × matter history.
"""

import logging
import os

from app.db import get_database_url
from app.embedding import get_embedding
from app.schemas import Suggestion, TimeEntry
from app.ollama_rationale import (
    build_batch_prompt,
    get_ollama_config,
    ollama_generate,
    parse_rationales_json,
)

logger = logging.getLogger(__name__)

# Two-stage ranking in one query:
# 1) text_stage: rank by text-only score (semantic + FTS), limit candidates
# 2) joined: add personalization (affinity, recency, rejection_factor) and re-rank
# %s order: embedding, narrative, user_id.
SUGGESTIONS_QUERY = """
WITH text_base AS (
    SELECT
        m.client_id,
        m.matter_id,
        m.client_name,
        m.matter_name,
        m.matter_description,
        m.practice_area,
        m.matter_type,
        m.related_keywords,
        (1 - (m.embedding <=> %s))::float AS semantic_score,
        COALESCE(ts_rank(m.search_vector, plainto_tsquery('english', %s)), 0)::float AS fts_score
    FROM matters m
    WHERE m.embedding IS NOT NULL
      AND COALESCE(m.status, 'open') = 'open'
),
text_stage AS (
    SELECT
        client_id,
        matter_id,
        client_name,
        matter_name,
        matter_description,
        practice_area,
        matter_type,
        related_keywords,
        semantic_score,
        fts_score,
        (0.7 * semantic_score + 0.3 * LEAST(1.0, fts_score * 5.0)) AS text_score
    FROM text_base
    ORDER BY text_score DESC
    LIMIT 50
),
feedback_agg AS (
    SELECT
        client_id,
        matter_id,
        COUNT(*) FILTER (WHERE action = 'accepted') AS accept_count,
        COUNT(*) FILTER (WHERE action = 'rejected') AS reject_count,
        MAX(created_at) AS last_event_at
    FROM feedback
    WHERE user_id = %s
    GROUP BY client_id, matter_id
),
joined AS (
    SELECT
        t.client_id,
        t.matter_id,
        t.client_name,
        t.matter_name,
        t.matter_description,
        t.practice_area,
        t.matter_type,
        t.related_keywords,
        t.semantic_score,
        t.fts_score,
        COALESCE(fa.accept_count, 0) AS accept_count,
        COALESCE(fa.reject_count, 0) AS reject_count,
        fa.last_event_at,
        -- affinity: only when there is enough history; otherwise neutral 0.5
        COALESCE(
            CASE
                WHEN (fa.accept_count + fa.reject_count) >= 3 THEN
                    LEAST(1.0, fa.accept_count::float / 5.0)
                ELSE
                    0.5
            END,
            0.5
        ) AS affinity,
        -- recency: exp(-days_since_last_event / 30) when there is enough history,
        -- otherwise neutral 0.5 (no history or too few events).
        COALESCE(
            CASE
                WHEN (fa.accept_count + fa.reject_count) >= 3 THEN
                    EXP(
                        -GREATEST(
                            0.0,
                            EXTRACT(EPOCH FROM (NOW() - fa.last_event_at)) / 86400.0
                        ) / 30.0
                    )
                ELSE
                    0.5
            END,
            0.5
        ) AS recency,
        -- rejection factor: soft penalty only when there is enough history; never below 0.7.
        COALESCE(
            CASE
                WHEN (fa.accept_count + fa.reject_count) >= 3 THEN
                    GREATEST(
                        0.7,
                        1.0 - LEAST(
                            1.0,
                            fa.reject_count::float
                            / GREATEST(1.0, (fa.accept_count + fa.reject_count)::float)
                        )
                    )
                ELSE
                    1.0
            END,
            1.0
        ) AS rejection_factor
    FROM text_stage t
    LEFT JOIN feedback_agg fa
        ON fa.client_id = t.client_id
       AND fa.matter_id = t.matter_id
)
SELECT
    client_id,
    matter_id,
    client_name,
    matter_name,
    matter_description,
    practice_area,
    matter_type,
    related_keywords,
    semantic_score,
    fts_score,
    accept_count,
    reject_count,
    last_event_at,
    affinity,
    recency,
    rejection_factor,
    LEAST(
        1.0,
        GREATEST(
            0.0,
            (
                0.6 * semantic_score
              + 0.25 * LEAST(1.0, fts_score * 5.0)
              + 0.1 * affinity
              + 0.05 * recency
            ) * rejection_factor
        )
    ) AS combined_score
FROM joined
ORDER BY combined_score DESC
LIMIT 10
"""


def _rationale(semantic: float, fts: float, affinity: float, recency: float) -> str:
    """
    Human-readable rationale built from qualitative bands instead of raw percentages.

    This is a default template that explains *why* a suggestion was surfaced
    in plain language, using the main signals we have.
    """
    reasons: list[str] = []

    # Text similarity (semantic)
    if semantic >= 0.75:
        reasons.append("the narrative is highly similar to this matter")
    elif semantic >= 0.5:
        reasons.append("the narrative is a reasonable textual match for this matter")
    else:
        reasons.append("there is only a weak textual match to this matter")

    # Keyword overlap (fts)
    fts_norm = min(1.0, fts * 5.0)
    if fts_norm >= 0.6:
        reasons.append("the narrative shares strong keyword overlap with the matter description")
    elif fts_norm >= 0.3:
        reasons.append("the narrative shares some keywords with the matter description")

    # Affinity (user × matter)
    if abs(affinity - 0.5) < 1e-6:
        # neutral / no or too little history — handled by recency text below
        pass
    elif affinity >= 0.8:
        reasons.append("you have billed to this matter frequently in prior entries")
    elif affinity >= 0.3:
        reasons.append("you have worked on this matter before")

    # Recency (user × matter time dimension)
    if abs(recency - 0.5) < 1e-6:
        reasons.append("we do not yet have history linking you to this matter")
    elif recency >= 0.7:
        reasons.append("you worked on this matter recently")
    elif recency >= 0.3:
        reasons.append("you have worked on this matter in the past, but not recently")

    # Fallback if, for some reason, no reasons were added
    if not reasons:
        return "Suggested based on a combination of text similarity and your past work history."

    # Build final sentence
    if len(reasons) == 1:
        detail = reasons[0]
    else:
        detail = ", ".join(reasons[:-1]) + f", and {reasons[-1]}"

    return f"Suggested because {detail}."


def get_suggestions_for_entry(entry: TimeEntry):
    """
    Embed the narrative, run one query for semantic + FTS + personalization features,
    return Suggestion list ranked by combined_score.
    """
    import psycopg
    from pgvector.psycopg import register_vector

    narrative_clean = entry.narrative.strip() or " "
    embedding = get_embedding(narrative_clean)

    url = get_database_url()
    with psycopg.connect(url) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                SUGGESTIONS_QUERY,
                (embedding, narrative_clean, entry.user_id),
            )
            rows = cur.fetchall()

    suggestions = []
    for row in rows:
        semantic = float(row[8])
        fts_raw = float(row[9])
        keyword_norm = min(1.0, fts_raw * 5.0)
        affinity = float(row[13])
        recency = float(row[14])
        combined = float(row[16])
        suggestions.append(
            Suggestion(
                client_id=row[0],
                matter_id=row[1],
                client_name=row[2],
                matter_name=row[3],
                score=combined,
                semantic_score=semantic,
                keyword_score=keyword_norm,
                affinity=affinity,
                recency=recency,
                rationale=_rationale(
                    semantic=semantic,
                    fts=fts_raw,
                    affinity=affinity,
                    recency=recency,
                ),
                rationale_source="template",
                llm_status="pending" if get_ollama_config().enabled else "disabled",
                llm_rationale=None,
            )
        )

    # NOTE: LLM rationales are hydrated asynchronously via a separate endpoint.

    # Low-confidence heuristic: if the top suggestion is below threshold, warn.
    # This threshold is a starting point and should be tuned with real feedback.
    LOW_CONFIDENCE_THRESHOLD = 0.55
    low_confidence = (not suggestions) or (suggestions[0].score < LOW_CONFIDENCE_THRESHOLD)
    return suggestions, low_confidence, rows


def generate_ollama_rationales_for_rows(entry: TimeEntry, rows) -> dict[tuple[str, str], str]:
    """
    Generate Ollama rationales for an existing suggestion result set (rows from SUGGESTIONS_QUERY).
    Returns mapping (client_id, matter_id) -> rationale.
    """
    cfg = get_ollama_config()
    if not cfg.enabled or not rows:
        return {}

    def _tokens(s: str) -> set[str]:
        import re
        return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) >= 3}

    narrative_clean = entry.narrative.strip() or " "
    narrative_terms = sorted(_tokens(narrative_clean))[:12]
    candidates = [
        {
            "client_id": r[0],
            "matter_id": r[1],
            "client_name": r[2],
            "matter_name": r[3],
            "matter_description": r[4] or "",
            "practice_area": r[5] or "",
            "matter_type": r[6] or "",
            "related_keywords": list(r[7] or []),
            "narrative_terms": narrative_terms,
            "keyword_overlap": sorted(_tokens(" ".join(list(r[7] or []))) & _tokens(narrative_clean))[:10],
            "semantic_score": float(r[8]),
            "fts_score": float(r[9]),
            "fts_norm": min(1.0, float(r[9]) * 5.0),
            "accept_count": int(r[10]),
            "reject_count": int(r[11]),
            "no_prior_history": (int(r[10]) + int(r[11])) < 3,
            "affinity": float(r[13]),
            "recency": float(r[14]),
            "rejection_factor": float(r[15]),
            "combined_score": float(r[16]),
            "confidence_band": (
                "high" if float(r[16]) >= 0.75 else ("medium" if float(r[16]) >= 0.55 else "low")
            ),
        }
        for r in rows
    ]

    prompt = build_batch_prompt(
        user_id=entry.user_id,
        entry_id=entry.entry_id,
        narrative=narrative_clean,
        candidates=candidates,
    )

    debug = os.getenv("OLLAMA_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    if debug:
        logger.info(
            "Ollama hydration attempt (model=%s url=%s timeout_s=%s candidates=%d prompt_chars=%d)",
            cfg.model,
            cfg.base_url,
            cfg.timeout_s,
            len(candidates),
            len(prompt),
        )
    text = ollama_generate(base_url=cfg.base_url, model=cfg.model, prompt=prompt, timeout_s=cfg.timeout_s)
    if debug:
        logger.info("Ollama hydration raw response (first 200 chars): %r", text[:200])
    return parse_rationales_json(text)
