# pgvector setup (Postgres side)

The app uses the **pgvector** extension. Your Postgres server must have it installed before the app runs.

## If you use Postgres via pgAdmin 4

pgAdmin is a client; the server is your local Postgres install.

### 1. Install the extension on the server

- **macOS (Homebrew):**  
  `brew install pgvector`  
  Then restart Postgres if it was already running.

- **macOS (EDB/Postgres.app):**  
  Install pgvector for your Postgres version (e.g. from [pgvector releases](https://github.com/pgvector/pgvector/releases)) or use a build that includes it.

- **Windows:**  
  Use the [pgvector Windows build](https://github.com/pgvector/pgvector#windows) or a Postgres distribution that bundles it.

### 2. Enable the extension in your database

In pgAdmin (or any SQL client), connect to your database and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The app’s startup logic also runs this if the extension is already installed, so the DB user must have permission to create extensions (or an admin must run it once).

### 3. Verify

In pgAdmin, open Query Tool and run:

```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

You should see one row. After that, set `DATABASE_URL` in `.env` and start the app.
