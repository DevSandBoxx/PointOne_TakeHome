"""
Phase 2: fetch ranked client/matter suggestions using one Postgres query.
Combines semantic (pgvector) and full-text (tsvector) scores.
"""

from app.db import get_database_url
from app.embedding import get_embedding
from app.schemas import Suggestion

# Single query: vector similarity + ts_rank, return both scores and row data.
# %s order: embedding, narrative, embedding, narrative.
SUGGESTIONS_QUERY = """
SELECT
    client_name,
    matter_name,
    (1 - (embedding <=> %s))::float AS semantic_score,
    coalesce(ts_rank(search_vector, plainto_tsquery('english', %s)), 0)::float AS fts_score
FROM matters
WHERE embedding IS NOT NULL
ORDER BY (1 - (embedding <=> %s)) DESC, ts_rank(search_vector, plainto_tsquery('english', %s)) DESC
LIMIT 20
"""

# Weights for combining semantic and FTS into a single 0–1 score.
# FTS ts_rank is often small (e.g. 0.01–0.2), so we scale it before blending.
SEMANTIC_WEIGHT = 0.65
FTS_WEIGHT = 0.35
FTS_SCALE = 5.0  # scale raw ts_rank so typical values contribute (min(1, fts * FTS_SCALE))


def _combined_score(semantic: float, fts: float) -> float:
    """Single 0–1 score from semantic and FTS scores."""
    fts_norm = min(1.0, float(fts) * FTS_SCALE)
    return round(SEMANTIC_WEIGHT * semantic + FTS_WEIGHT * fts_norm, 4)


def _rationale(semantic: float, fts: float) -> str:
    """Human-readable breakdown for the suggestion."""
    return f"Semantic: {round(semantic * 100)}%; Keyword: {round(fts * 100)}%"


def get_suggestions_for_entry(narrative: str):
    """
    Embed the narrative, run one query for semantic + FTS scores, return Suggestion list.
    """
    import psycopg
    from pgvector.psycopg import register_vector

    narrative_clean = narrative.strip() or " "
    embedding = get_embedding(narrative_clean)

    url = get_database_url()
    with psycopg.connect(url) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                SUGGESTIONS_QUERY,
                (embedding, narrative_clean, embedding, narrative_clean),
            )
            rows = cur.fetchall()

    return [
        Suggestion(
            client_name=row[0],
            matter_name=row[1],
            score=_combined_score(row[2], row[3]),
            rationale=_rationale(row[2], row[3]),
        )
        for row in rows
    ]
