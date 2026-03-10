"""
Seed the Matters table from a JSON file. Runs as a background task on app startup.

Preparation (embeddings, search_vector) is stored in the table and reused—queries
only read; nothing is recomputed per request. When the source data changes, rebuild
the index by running this module (e.g. `python -m app.seed_matters`) or calling
rebuild_matters().

Expects JSON array of client/matter objects with: ClientId, ClientName, MatterId,
MatterName; optional: MatterDescription, PracticeArea, MatterType, Status,
RelatedKeywords (list), InvolvedTimekeepers (list). Keys may be snake_case or
PascalCase. Computes embeddings and search_vector from combined text on insert; both are stored and reused.
"""

import json
import logging
from pathlib import Path

from app.db import get_database_url

logger = logging.getLogger(__name__)

# Embedding dimension for all-MiniLM-L6-v2
EMBEDDING_DIM = 384

MATTERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS matters (
    id SERIAL PRIMARY KEY,
    client_id TEXT NOT NULL,
    client_name TEXT NOT NULL,
    matter_id TEXT NOT NULL,
    matter_name TEXT NOT NULL,
    matter_description TEXT,
    practice_area TEXT,
    matter_type TEXT,
    status TEXT,
    related_keywords TEXT[],
    involved_timekeepers TEXT[],
    embedding vector(384),
    search_vector tsvector,
    UNIQUE (client_id, matter_id)
)
"""

MATTERS_EMBEDDING_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS matters_embedding_idx ON matters
    USING hnsw (embedding vector_cosine_ops)
"""

MATTERS_SEARCH_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS matters_search_vector_idx ON matters
    USING gin (search_vector)
"""


def ensure_matters_table(conn) -> None:
    """Create matters table and indexes if they do not exist."""
    with conn.cursor() as cur:
        cur.execute(MATTERS_TABLE_SQL)
        cur.execute(MATTERS_EMBEDDING_INDEX_SQL)
        cur.execute(MATTERS_SEARCH_INDEX_SQL)
    conn.commit()


def _get_embedding_model():
    """Lazy-load sentence-transformers model (heavy on first use)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def _get(row: dict, *keys: str) -> str | None:
    """Get first present key from row (supports PascalCase or snake_case)."""
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def _get_list(row: dict, *key_pairs: tuple[str, str]) -> list[str]:
    """Get optional list from row; keys can be (snake_case, PascalCase)."""
    for snake, pascal in key_pairs:
        val = row.get(snake) or row.get(pascal)
        if val is not None:
            return list(val) if isinstance(val, list) else [val]
    return []


def _normalize_row(row: dict, index: int) -> dict:
    """Normalize a JSON row to internal keys and required fields."""
    required = {"client_id", "client_name", "matter_id", "matter_name"}
    aliases = [
        ("client_id", "ClientId"),
        ("client_name", "ClientName"),
        ("matter_id", "MatterId"),
        ("matter_name", "MatterName"),
    ]
    out = {}
    for snake, pascal in aliases:
        v = _get(row, snake, pascal)
        if v is None and snake in required:
            raise ValueError(f"Row {index}: missing required field {snake}/{pascal}")
        out[snake] = v or ""
    out["matter_description"] = _get(row, "matter_description", "MatterDescription") or None
    out["practice_area"] = _get(row, "practice_area", "PracticeArea") or None
    out["matter_type"] = _get(row, "matter_type", "MatterType") or None
    out["status"] = _get(row, "status", "Status") or None
    out["related_keywords"] = _get_list(row, ("related_keywords", "RelatedKeywords"))
    out["involved_timekeepers"] = _get_list(row, ("involved_timekeepers", "InvolvedTimekeepers"))
    return out


def load_matters_json(path: Path) -> list[dict]:
    """Load and validate matters from JSON file; normalize to internal keys."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("JSON must be an array of matter objects")
    return [_normalize_row(row, i) for i, row in enumerate(data) if isinstance(row, dict)]


def seed_matters(json_path: Path) -> int:
    """
    Load matters from JSON, compute embeddings, and insert into the matters table.
    Returns the number of rows inserted.
    """
    import psycopg
    from pgvector.psycopg import register_vector

    url = get_database_url()
    rows = load_matters_json(json_path)
    if not rows:
        logger.info("No matters in %s", json_path)
        return 0

    def embedding_text(r: dict) -> str:
        parts = [
            r["client_name"],
            r["matter_name"],
            r.get("matter_description") or "",
            r.get("practice_area") or "",
            r.get("matter_type") or "",
            " ".join(r.get("related_keywords") or []),
        ]
        return " ".join(p for p in parts if p).strip()

    model = _get_embedding_model()
    texts = [embedding_text(r) for r in rows]
    # pgvector expects array-like; sentence_transformers returns ndarray
    embeddings = model.encode(texts)

    with psycopg.connect(url) as conn:
        register_vector(conn)
        ensure_matters_table(conn)
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO matters (
                    client_id, client_name, matter_id, matter_name,
                    matter_description, practice_area, matter_type, status,
                    related_keywords, involved_timekeepers, embedding, search_vector
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_tsvector('english', %s))
                ON CONFLICT (client_id, matter_id) DO UPDATE SET
                    client_name = EXCLUDED.client_name,
                    matter_name = EXCLUDED.matter_name,
                    matter_description = EXCLUDED.matter_description,
                    practice_area = EXCLUDED.practice_area,
                    matter_type = EXCLUDED.matter_type,
                    status = EXCLUDED.status,
                    related_keywords = EXCLUDED.related_keywords,
                    involved_timekeepers = EXCLUDED.involved_timekeepers,
                    embedding = EXCLUDED.embedding,
                    search_vector = EXCLUDED.search_vector
                """,
                [
                    (
                        r["client_id"],
                        r["client_name"],
                        r["matter_id"],
                        r["matter_name"],
                        r.get("matter_description"),
                        r.get("practice_area"),
                        r.get("matter_type"),
                        r.get("status"),
                        r.get("related_keywords") or [],
                        r.get("involved_timekeepers") or [],
                        emb,
                        embedding_text(r),
                    )
                    for r, emb in zip(rows, embeddings)
                ],
            )
        conn.commit()
        count = len(rows)
    logger.info("Seeded %d matters from %s", count, json_path)
    return count


def get_default_matters_json_path() -> Path:
    """Project-root path to the default matters JSON file."""
    return Path(__file__).resolve().parent.parent / "data" / "matters.json"


def rebuild_matters(json_path: Path | None = None) -> int:
    """
    Rebuild the matters index from source data: truncate the table, then seed.
    Use this when the JSON (or other source) has changed and you want the
    stored embeddings and search_vector to match exactly.

    Returns the number of rows inserted. Uses default data/matters.json if
    json_path is None.
    """
    import psycopg
    from pgvector.psycopg import register_vector

    if json_path is None:
        json_path = get_default_matters_json_path()
    if not json_path.exists():
        raise FileNotFoundError(f"Matters JSON not found: {json_path}")

    url = get_database_url()
    with psycopg.connect(url) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS matters CASCADE")
        conn.commit()
    # Recreate table with current schema and seed
    return seed_matters(json_path)


def run_seed_matters_background(json_path: Path | None = None) -> None:
    """
    Run seed in a way suitable for background execution (e.g. from lifespan).
    Uses default path data/matters.json relative to project root if json_path is None.
    Logs and swallows errors so app startup is not failed by seed failures.
    """
    if json_path is None:
        json_path = get_default_matters_json_path()
    if not json_path.exists():
        logger.warning("Matters JSON not found at %s; skipping seed", json_path)
        return
    try:
        seed_matters(json_path)
    except Exception as e:
        logger.exception("Failed to seed matters from %s: %s", json_path, e)


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    # Simple CLI:
    #   python -m app.seed_matters                -> seed from default data/matters.json
    #   python -m app.seed_matters path/to.json   -> seed from given JSON
    #   python -m app.seed_matters --rebuild      -> drop + rebuild from default JSON
    #   python -m app.seed_matters path/to.json --rebuild -> drop + rebuild from given JSON
    argv = sys.argv[1:]
    rebuild_flag = "--rebuild" in argv
    args = [a for a in argv if a != "--rebuild"]

    if args:
        path = Path(args[0])
    else:
        path = get_default_matters_json_path()

    if rebuild_flag:
        n = rebuild_matters(path)
        print(f"Rebuilt matters index: {n} rows from {path}")
    else:
        n = seed_matters(path)
        print(f"Seeded matters: {n} rows from {path}")
