"""
Database connection and pgvector setup.

Expects DATABASE_URL in the environment (e.g. postgresql://user:pass@localhost:5432/dbname).
"""

import os

import psycopg
from pgvector.psycopg import register_vector


def get_database_url() -> str:
    """Database URL from environment. Raises if not set."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL is not set. Example: postgresql://user:pass@localhost:5432/pointone"
        )
    return url


def check_connection() -> None:
    """
    Verify we can connect to the database and that the pgvector extension exists.
    Raises if the database is unreachable or pgvector is not available.
    """
    url = get_database_url()
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    # Ensure extension (requires autocommit for CREATE EXTENSION)
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Register vector type for future use (e.g. when you add vector columns)
    with psycopg.connect(url) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
