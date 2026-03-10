"""
Phase 2: ranked client/matter suggestions via one Postgres query (semantic + FTS)
with additive personalization features (affinity, recency, rejection penalty).

See docs/SUGGESTIONS_SCORING.md for what the base query returns and how scores
are combined; this module extends that with user × matter history.
"""

from app.db import get_database_url
from app.embedding import get_embedding
from app.schemas import Suggestion, TimeEntry

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
        t.semantic_score,
        t.fts_score,
        -- affinity: saturating at 1.0 after ~5 accepted events
        COALESCE(LEAST(1.0, fa.accept_count::float / 5.0), 0.0) AS affinity,
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
    semantic_score,
    fts_score,
    affinity,
    recency,
    rejection_factor,
    (
        (
            0.6 * semantic_score
          + 0.25 * LEAST(1.0, fts_score * 5.0)
          + 0.1 * affinity
          + 0.05 * recency
        ) * rejection_factor
    ) AS combined_score
FROM joined
ORDER BY combined_score DESC
LIMIT 20
"""


def _rationale(semantic: float, fts: float, affinity: float, recency: float) -> str:
    """Human-readable breakdown of the main components for the suggestion."""
    recency_str = (
        "No history" if abs(recency - 0.5) < 1e-6 else f"{round(recency * 100)}%"
    )
    return (
        f"Semantic: {round(semantic * 100)}%; "
        f"Keyword: {round(fts * 100)}%; "
        f"Affinity: {round(affinity * 100)}%; "
        f"Recency: {recency_str}"
    )


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

    return [
        Suggestion(
            client_id=row[0],
            matter_id=row[1],
            client_name=row[2],
            matter_name=row[3],
            score=float(row[9]),
            rationale=_rationale(
                semantic=float(row[4]),
                fts=float(row[5]),
                affinity=float(row[6]),
                recency=float(row[7]),
            ),
        )
        for row in rows
    ]
