-- Matters table: client/matter records with vector and full-text search support.
-- Fields match client/matter record description (snake_case in DB).
-- search_vector is set on insert by the app (to_tsvector('english', ...)); not generated to avoid immutability errors.

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
);

CREATE INDEX IF NOT EXISTS matters_embedding_idx ON matters
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS matters_search_vector_idx ON matters
    USING gin (search_vector);
