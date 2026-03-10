# Suggestions: search query and score combination

Phase 2 uses a single Postgres query to rank client/matter suggestions by semantic (pgvector) and full-text (tsvector) similarity. This doc describes what the query returns and how we process and combine the scores.

---

## Why score-based fusion (not reciprocal rank fusion)

**Reciprocal Rank Fusion (RRF)** is a common way to merge two or more *ranked lists*: each list comes from a separate retriever; you assign a score per item like `1 / (k + rank)` from each list and sum across lists, then re-rank by that sum. RRF is rank-based: it ignores the actual similarity or relevance *scores* and only uses positions in each list.

We use **score-based fusion** instead:

1. **Single list, two scores per row** — Our search is one Postgres query that returns one result set. Every row has both a semantic score and an FTS score. We never have “rank in the semantic list” vs “rank in the keyword list”; we have two numeric signals per candidate. So there is no natural “fusion of two rank lists” to apply RRF to.

2. **We want a meaningful confidence value** — The API exposes a single `score` in [0, 1] so the UI can show “how confident” the suggestion is. Semantic similarity is already a natural confidence (0 = unrelated, 1 = same meaning). Blending it with a normalized keyword score in the same range keeps the combined value interpretable. RRF produces a fused rank and a derived score that is not “confidence” in the same sense.

3. **Rationale uses the scores** — We show “Semantic: 92%; Keyword: 15%” so users see why a suggestion was chosen. That only makes sense if we keep and normalize the underlying scores. With RRF we would be discarding score magnitude and only using rank, so we couldn’t report a clear semantic vs keyword breakdown.

So we intentionally combine in **score space** (after normalizing FTS into a 0–1 band) rather than using RRF. If we later split into two separate retrieval paths (e.g. vector search and FTS as separate queries) and merge their result lists, RRF would become a reasonable alternative and we could document it here.

---

## What the search query returns

The query in `app/suggestions.py` returns **one row per matter** with exactly **four columns**:

| Column           | Type  | Description                                                                                                                                                                                                                                             |
| ---------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `client_name`    | text  | From `matters.client_name`.                                                                                                                                                                                                                             |
| `matter_name`    | text  | From `matters.matter_name`.                                                                                                                                                                                                                             |
| `semantic_score` | float | `(1 - (embedding <=> $narrative_embedding))` — cosine similarity between the narrative embedding and the matter’s stored embedding. In **[0, 1]**; 1 = identical direction, 0 = orthogonal.                                                             |
| `fts_score`      | float | `ts_rank(search_vector, plainto_tsquery('english', narrative))` — PostgreSQL full-text rank of the matter’s `search_vector` against the narrative as a query. Non-negative, unbounded; typical values are small (e.g. 0.01–0.3) when a few terms match. |

- Rows are **ordered** by `semantic_score DESC`, then `fts_score DESC`.
- **Limit** 20 rows.
- Only rows with **non-null** `embedding` are considered.

---

## Processing on the result

We do **not** return the raw scores directly. For each row we:

1. **Combined score (0–1)** — Blend `semantic_score` and `fts_score` into a single score so the API exposes one confidence value (see below).
2. **Rationale** — Build a short string from the raw scores so the user sees why the suggestion was ranked (e.g. `"Semantic: 92%; Keyword: 15%"`).
3. **Suggestion model** — Map `(client_name, matter_name, combined score, rationale)` into the `Suggestion` schema returned by the API.

No other filtering or re-ranking is applied; the order from the query is preserved.

---

## Why and how we combine the scores

### Semantic score

- Already in **[0, 1]**, so it is used directly as a confidence component.
- Captures **meaning** (e.g. “contract dispute” vs “supply agreement”) even when wording differs.

### Full-text score (ts_rank)

- **Not normalized**: it can be 0 or small for weak keyword overlap and rarely exceeds ~0.1–0.3 for strong matches.
- If we blended it **raw** with semantic, keyword match would barely affect the combined score.
- So we **scale** it into a 0–1 band with a multiplier **FTS_SCALE = 5**: we use `min(1, fts_score * FTS_SCALE)` so that typical good keyword matches (e.g. 0.1–0.2) contribute meaningfully (0.5–1.0) without letting a single huge `ts_rank` dominate.

### Weights

- **SEMANTIC_WEIGHT = 0.65**, **FTS_WEIGHT = 0.35**.
- Semantic similarity is the main signal for “same matter”; keyword match is a useful boost when the narrative explicitly mentions client/matter terms.

### Formula

```
combined = SEMANTIC_WEIGHT * semantic_score + FTS_WEIGHT * min(1, fts_score * FTS_SCALE)
```

Result is in **[0, 1]** by construction and rounded to 4 decimals.
