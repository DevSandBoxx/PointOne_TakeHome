# Suggestions: search query and score combination

Phase 2 uses a two-stage Postgres query to rank client/matter suggestions by:

- **Semantic similarity** (pgvector)
- **Full-text similarity** (tsvector)
- **User × matter history** (affinity, recency, rejection)

This doc describes how the query works and how we process and combine the scores.

---

## Why score-based fusion (not reciprocal rank fusion)

**Reciprocal Rank Fusion (RRF)** is a common way to merge two or more *ranked lists*: each list comes from a separate retriever; you assign a score per item like `1 / (k + rank)` from each list and sum across lists, then re-rank by that sum. RRF is rank-based: it ignores the actual similarity or relevance *scores* and only uses positions in each list.

We use **score-based fusion** instead:

1. **Single list, two scores per row** — Our search is one Postgres query that returns one result set. Every row has both a semantic score and an FTS score. We never have “rank in the semantic list” vs “rank in the keyword list”; we have two numeric signals per candidate. So there is no natural “fusion of two rank lists” to apply RRF to.

2. **We want a meaningful confidence value** — The API exposes a single `score` in [0, 1] so the UI can show “how confident” the suggestion is. Semantic similarity is already a natural confidence (0 = unrelated, 1 = same meaning). Blending it with a normalized keyword score in the same range keeps the combined value interpretable. RRF produces a fused rank and a derived score that is not “confidence” in the same sense.

3. **Rationale uses the scores** — We show “Semantic: 92%; Keyword: 15%” so users see why a suggestion was chosen. That only makes sense if we keep and normalize the underlying scores. With RRF we would be discarding score magnitude and only using rank, so we couldn’t report a clear semantic vs keyword breakdown.

So we intentionally combine in **score space** (after normalizing FTS into a 0–1 band) rather than using RRF. If we later split into two separate retrieval paths (e.g. vector search and FTS as separate queries) and merge their result lists, RRF would become a reasonable alternative and we could document it here.

---

## What the search query returns (two stages)

The query in `app/suggestions.py` runs in **two stages**:

### Stage 1 – Text-only ranking (`text_stage`)

1. Compute **semantic_score** for each open matter:

   ```sql
   semantic_score = (1 - (embedding <=> $narrative_embedding))::float
   ```

   - This is cosine similarity in **[0, 1]** between the narrative embedding and the stored matter embedding.

2. Compute **fts_score** via full-text search:

   ```sql
   fts_score = ts_rank(search_vector, plainto_tsquery('english', narrative))
   ```

   - Non-negative, unbounded; typical values are small (e.g. 0.01–0.3) when a few terms match.

3. Filter to matters with `status = 'open'` and non-null embedding.

4. Compute a **text-only score**:

   ```sql
   text_score = 0.7 * semantic_score + 0.3 * LEAST(1.0, fts_score * 5.0)
   ```

5. Order by `text_score DESC` and keep the **top 50** candidates. This becomes the **candidate pool** for personalization.

### Stage 2 – Personalization and final ranking (`joined`)

For each candidate from Stage 1 and for the current `user_id`, we compute:

| Column             | Type   | Description |
|--------------------|--------|-------------|
| `client_id`        | text   | From `matters.client_id`. |
| `matter_id`        | text   | From `matters.matter_id`. |
| `client_name`      | text   | From `matters.client_name`. |
| `matter_name`      | text   | From `matters.matter_name`. |
| `semantic_score`   | float  | From Stage 1. |
| `fts_score`        | float  | From Stage 1. |
| `affinity`         | float  | User × matter affinity (0–1), neutral 0.5 when little/no history. |
| `recency`          | float  | User × matter recency (0–1), neutral 0.5 when little/no history. |
| `rejection_factor` | float  | Soft penalty in [0.7, 1.0] when there is enough history; 1.0 otherwise. |
| `combined_score`   | float  | Final ranking score in [0, 1] used by the API. |

Notes:

- **Affinity**: based on per-user accepts (`accept_count`), only when there are at least 3 feedback events (accept+reject). Below that, it is set to **0.5** (neutral).
- **Recency**: exponential decay based on time since last feedback, only when there are at least 3 events. Otherwise **0.5** (neutral).
- **Rejection factor**: 1 minus the user-specific rejection rate, but:
  - Only applied when there are at least 3 events.
  - **Capped at 0.7** so it cannot completely wipe out a strong text match.
  - Default is 1.0 when there is little/no history.

---

## Processing on the result

We do **not** return the raw scores directly. For each row we:

1. **Combined score (0–1)** — We blend semantic, FTS, affinity, and recency into a single score and then apply a soft rejection penalty (see below). This is what the API exposes as `score`.
2. **Rationale** — A template-based rationale builder converts the main signals into one human-readable explanation (e.g. “Suggested because the narrative is highly similar to this matter and you worked on this matter recently.”).
3. **Suggestion model** — We map `(client_id, matter_id, client_name, matter_name, combined score, rationale)` into the `Suggestion` schema returned by the API.

The final query orders by `combined_score DESC` and returns the top 20 suggestions from the Stage‑2 candidate pool.

---

## Why and how we combine the scores

### Stage 1 – Text-only score

- **Semantic score**:
  - Already in **[0, 1]**, used directly as the primary relevance signal.
  - Captures **meaning** (e.g. “contract dispute” vs “supply agreement”) even when wording differs.

- **Full-text score (ts_rank)**:
  - Not normalized by default; we scale it into [0, 1] with `min(1, fts_score * 5.0)` so typical values contribute meaningfully.

Stage‑1 text score:

```sql
text_score = 0.7 * semantic_score + 0.3 * LEAST(1.0, fts_score * 5.0)
```

This is used **only for retrieval** and to define the 50‑item candidate pool.

### Stage 2 – Final combined score

Within the candidate pool, we compute:

- **Affinity** (`affinity`):
  - When there are at least 3 feedback events for (user, matter), we use:
    - `LEAST(1.0, accept_count / 5.0)` — saturates at 1.0 after ~5 accepts.
  - Otherwise, we set it to **0.5** (neutral / no or too little history).

- **Recency** (`recency`):
  - When there are at least 3 events:
    - `exp(-days_since_last_event / 30.0)` — exponential decay with ~30‑day scale.
  - Otherwise, **0.5** (neutral).

- **Rejection factor** (`rejection_factor`):
  - When there are at least 3 events:
    - `1 ‑ rejection_rate`, where `rejection_rate = reject_count / (accept_count + reject_count)`.
    - Capped so it never drops below **0.7**.
  - Otherwise, **1.0** (no effect).

The final combined score is:

```sql
combined_score =
  (
    0.6 * semantic_score
  + 0.25 * LEAST(1.0, fts_score * 5.0)
  + 0.1 * affinity
  + 0.05 * recency
  )
  * rejection_factor
```

Intuition:

- **Semantic + FTS (0.85 total)** are the primary relevance drivers.
- **Affinity + recency (0.15 total)** personalize within the already relevant set.
- **Rejection factor** is a **soft, user-specific down-weight**, only when there is enough evidence and never so strong that it can override an obviously good text match.

The result is clamped to **[0, 1]** by construction and used directly as the `score` returned in `Suggestion`.
