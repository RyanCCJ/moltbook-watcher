# Data Flow and Safe Reset Guide

This document explains:
- how data moves through the service
- where data is stored
- how to reset only this service's data (without touching other services)

## 1. Storage map

- PostgreSQL (durable state)
  - `candidate_posts`
  - `score_cards`
  - `review_items`
  - `publish_jobs`
  - `published_post_records`
  - `follow_up_candidates`
  - `notification_events`
- Redis (queue/cache runtime; optional in current flow)
- Logs (stdout/file depending on your supervisor setup)

## 2. Pipeline data flow

1. Ingestion (`/ops/ingestion/run` or scheduler)
   - fetch posts from Moltbook API (`sort`, `limit`) and apply local `window` time filtering
   - fetch top comments for each new post (`GET /posts/{id}/comments?sort=top&limit=5`)
   - deduplicate
   - score with Ollama (post + top comments context)
   - write `candidate_posts` + `score_cards`
   - candidate status: `seen -> scored -> queued`
2. Review build (same ingestion cycle)
   - create `review_items` for queued candidates not yet reviewed
   - snapshot top comments and optional translated comments
   - generate `threads_draft` for high-scoring candidates
3. Review action (`/review-items/{id}/decision`)
   - `approved` / `rejected` / `archived`
4. Publish (`/ops/publish/run` or scheduler)
   - schedule approved candidates into `publish_jobs`
   - publish with `review_items.threads_draft` when available, otherwise fallback to raw content
   - write `published_post_records` on success
   - retries and terminal notification on failures

## 3. Safety rules before reset

- Stop API and worker first.
- Confirm your `.env` points to dedicated resources:
  - dedicated PostgreSQL database (recommended)
  - dedicated Redis DB index (recommended, not DB 0)
- Never use `FLUSHALL`.

Check current runtime target quickly:

```bash
curl http://127.0.0.1:8000/health
```

Look at:
- `database_target`
- `redis_target`

## 4. Safe reset script (recommended)

Use:
- `scripts/reset_state.py`

It only resets this service's known PostgreSQL tables.  
For Redis, it supports:
- prefix delete (safer for shared Redis)
- `FLUSHDB` on the configured DB index (blocked for DB 0 unless explicitly allowed)

### 4.1 Reset PostgreSQL tables only

```bash
uv run python scripts/reset_state.py --target db --yes
```

### 4.2 Reset Redis keys by prefix only

```bash
uv run python scripts/reset_state.py \
  --target redis \
  --redis-mode prefix \
  --redis-prefix "moltbook:" \
  --yes
```

### 4.3 Reset Redis DB index (only if that DB index is dedicated)

```bash
uv run python scripts/reset_state.py \
  --target redis \
  --redis-mode flushdb \
  --yes
```

If your configured Redis index is `0`, script blocks by default.  
Only bypass if you are absolutely sure DB 0 is dedicated:

```bash
uv run python scripts/reset_state.py \
  --target redis \
  --redis-mode flushdb \
  --allow-redis-db0-flush \
  --yes
```

### 4.4 Reset DB + Redis together

```bash
uv run python scripts/reset_state.py --target all --yes
```

## 5. Manual reset (advanced)

### PostgreSQL (truncate app tables only)

```sql
TRUNCATE TABLE
  notification_events,
  follow_up_candidates,
  published_post_records,
  publish_jobs,
  review_items,
  score_cards,
  candidate_posts
RESTART IDENTITY CASCADE;
```

### Redis (configured DB index only)

```bash
redis-cli -u "redis://<HOST>:<PORT>/<DB_INDEX>" FLUSHDB
```

Use only when that DB index is dedicated.

## 6. Validate after reset

1. Recreate schema (idempotent):

```bash
uv run python scripts/migrate.py
```

2. Run one minimal ingestion smoke:

```bash
uv run python scripts/ops_cli.py ingest --window past_hour --sort top --limit 1
uv run python scripts/ops_cli.py review-list --status pending --limit 10
```
