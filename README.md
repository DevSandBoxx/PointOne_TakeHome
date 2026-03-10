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
