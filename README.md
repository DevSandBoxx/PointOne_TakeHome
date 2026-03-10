## PointOne – Client/Matter Suggestion Prototype

This project is a prototype classification system that, given a **time entry**, returns a ranked list of **client/matter suggestions** with:

- `ClientName`, `MatterName`
- `Score` (0–1 confidence)
- `Rationale` (human-readable explanation)

Backend: **FastAPI + Postgres + pgvector**  
Frontend: static **HTML/JS** served by FastAPI

---

## 1. Clone the repo

```bash
git clone <your-repo-url> PointOne
cd PointOne
```

> Replace `<your-repo-url>` with the actual Git remote when you publish this repo.

---

## 2. Python environment (conda) and dependencies

### 2.1 Create and activate the conda env

From the project root:

```bash
conda create -n pointone_take_home python=3.11 -y
conda activate pointone_take_home
```

### 2.2 Install Python requirements

```bash
pip install -r requirements.txt
```

This installs:

- `fastapi`, `uvicorn[standard]` – API server
- `psycopg[binary]` – Postgres driver
- `pgvector` – pgvector type support for psycopg
- `python-dotenv` – load `.env`
- `sentence-transformers` – embedding model (`all-MiniLM-L6-v2`)
- `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov` – for the test suite

---

## 3. Postgres + pgvector setup

You need a local Postgres instance and the `pgvector` extension installed.

### 3.1 Install Postgres and pgvector

On **macOS with Homebrew**:

```bash
brew install postgresql
brew install pgvector
brew services start postgresql
```

On **Linux**:

- Install Postgres via your distro (e.g. `apt install postgresql`).
- Install pgvector per the instructions at `https://github.com/pgvector/pgvector`.

On **Windows**:

- Install Postgres (e.g. via EDB installer).
- Install pgvector from the Windows section of the pgvector docs.

See `docs/PGVECTOR_SETUP.md` for platform-specific notes.

### 3.2 Create database and enable pgvector

1. Connect to Postgres (psql or pgAdmin) and create a DB, e.g.:

   ```sql
   CREATE DATABASE pointone;
   ```

2. Connect to that DB and enable pgvector:

   ```sql
   \c pointone
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

The app will also try to run `CREATE EXTENSION IF NOT EXISTS vector` at startup, so the DB user must have permission to create extensions (or an admin should run this once).

---

## 4. Environment variables

The app expects `DATABASE_URL` to be set. There are two files in the repo that show the shape:

- `.env` – your local environment file (ignored by git)
- `example-env` – example contents (safe to commit)

Typical value:

```env
DATABASE_URL=postgresql://postgres:pointone@localhost:5432/pointone
```

Steps:

```bash
cp example-env .env
# then edit .env to match your local Postgres user/password/DB
```

The app loads `.env` on startup.

---

## 5. Initialize the Matters index

The app uses a `matters` table with:

- text fields (`client_name`, `matter_name`, `matter_description`, etc.)
- `embedding vector(384)` (pgvector) for semantic search
- `search_vector tsvector` for full-text search

Source data lives in:

- `data/matters.json` – sample client/matter records with metadata.

There are two main ways to seed:

### 5.1 One-off seed (upsert)

From the project root (with env activated and `.env` set):

```bash
python -m app.seed_matters
```

This will:

- Create the `matters` table and indexes if they do not exist.
- Load all matters from `data/matters.json`.
- Compute embeddings using `sentence-transformers`.
- Upsert rows with `ON CONFLICT (client_id, matter_id) DO UPDATE SET ...`.

> This is **incremental**: new or changed rows are inserted/updated; others are left as-is.

### 5.2 Full rebuild (drop + reseed)

Use this rarely, e.g. when schema changes or you want DB state to exactly match the JSON (including deletions).

```bash
python -m app.seed_matters --rebuild
```

This will:

- `DROP TABLE IF EXISTS matters CASCADE;`
- Recreate the table and indexes.
- Seed from `data/matters.json`.

You can also provide an explicit JSON path:

```bash
python -m app.seed_matters path/to/matters.json --rebuild
```

See `docs/MATTERS_INDEX.md` for more details on storage and rebuilds.

---

## 6. Running the API + UI

From the project root (conda env activated, DB up, `.env` set):

```bash
uvicorn app.main:app --reload
```

This will:

- Load environment variables.
- Check DB connectivity and `pgvector` extension.
- Ensure `feedback` table exists.
- Start a background task to seed `matters` (upsert) from `data/matters.json` if present.

### 6.1 UI

Open:

- `http://127.0.0.1:8000/` – Time entry UI

You can:

- Type a **narrative** (e.g. “Drafted term sheet for Series A round”).
- Optionally set hours, date, current client/matter.
- Click **Get suggestions** to see ranked client/matter suggestions with:
  - score (0–1, shown as %)
  - rationale (text-based + feedback-based)
- Click **Accept** or **Reject** on a suggestion to send feedback (`POST /feedback`).

### 6.2 API (OpenAPI docs)

Visit:

- `http://127.0.0.1:8000/docs`

Key endpoints:

- `POST /suggestions` – body: `TimeEntry`, response: `SuggestionsResponse` (`low_confidence` + `suggestions[]`).
- `POST /feedback` – body: `FeedbackRequest` (user_id, entry_id, client_id, matter_id, action).

---

## 7. How scoring works (high level)

For each time entry:

1. Embed the narrative with `sentence-transformers/all-MiniLM-L6-v2`.
2. **Stage 1 (text ranking)**:

- Compute semantic score via pgvector (`embedding <=> narrative_embedding`).
- Compute FTS score via PostgreSQL `ts_rank(search_vector, plainto_tsquery(...))`.
- Filter to `status = 'open'`.
- Rank by a text-only score and take top 50.

3. **Stage 2 (personalization)**:

- Join with feedback for this user to compute:
  - Affinity (user × matter history, neutral when little/no history).
  - Recency (how recently the user interacted with this matter, neutral when no history).
  - Rejection factor (soft penalty when there is enough history; capped so it can’t fully wipe out good matches).
- Combine semantic, FTS, affinity, recency, and rejection factor into a single `score` in [0, 1].

4. **Low confidence**:

- If the top score is below a threshold, the API sets `low_confidence = true` and the UI shows a warning.

5. **Rationale**:

- A template-based rationale builder converts the individual signals into a human-readable explanation (e.g. “Suggested because the narrative is highly similar to this matter and you worked on this matter recently.”).

See `docs/SUGGESTIONS_SCORING.md` for the detailed SQL and weighting.

---

## 8. Feedback loop

- UI calls `POST /feedback` on Accept/Reject.
- Backend writes to a `feedback` table:
- `user_id`, `entry_id`, `client_id`, `matter_id`, `action`, `created_at`.
- Scoring uses this per user × matter to:
- Compute **affinity** (how often the user accepted that matter).
- Compute **recency** (how recent the last interaction was).
- Apply a **soft rejection penalty** when there is enough evidence.

This forms a **closed loop** where user behavior gradually adjusts rankings over time without retraining embeddings for every request.

---

## 9. Testing

From the project root (with the conda env activated and dependencies installed):

```bash
python -m pytest tests/ -v
```

- **Unit tests** cover schemas, embedding (dimension, empty input), rationale builder, seed_matters helpers (`_get`, `_get_list`, `_normalize_row`, `load_matters_json`), and `get_database_url`.
- **API tests** use FastAPI’s `TestClient` with mocked DB and suggestions so no real Postgres is required for the suite.
- **Optional integration tests** in `tests/test_db.py` (ensure feedback table, record feedback) are skipped unless `DATABASE_URL` points at a real database (i.e. not the default test placeholder). Run with a real DB URL to exercise them.

Coverage report:

```bash
python -m pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## 10. Ollama rationales (LLM explanations)

By default, the API returns a **template-based** rationale.
If you’ve installed Ollama, you can optionally have the backend generate rationales via a single local Ollama call per `/suggestions` request (best-effort; falls back to template if Ollama is down or returns invalid JSON).

1. Start Ollama:

```bash
ollama serve
```

2. Pull a model (example):

```bash
ollama pull llama3.1
```

3. Enable in `.env`:

```env
OLLAMA_RATIONALE_ENABLED=true
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_TIMEOUT_S=4.0
```
