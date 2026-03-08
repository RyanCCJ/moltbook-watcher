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
- Logs (stdout/file depending on your supervisor setup)

## 2. Pipeline data flow

1. Ingestion (`/ops/ingestion/run` or scheduler)
   - fetch posts from Moltbook API using upstream `time`, `sort`, and `limit` parameters
   - fetch top comments for each new post (`GET /posts/{id}/comments?sort=top&limit=5`)
   - deduplicate
   - score with Ollama (post + top comments context)
   - write `candidate_posts` + `score_cards.route_decision`
   - candidate status:
     - `seen -> scored -> archived` when `final_score < REVIEW_MIN_SCORE`
     - `seen -> scored -> queued` when `final_score >= REVIEW_MIN_SCORE`
     - `seen -> scored -> queued -> approved` when semi-auto mode fast-tracks the post
2. Review build (same ingestion cycle)
   - create `review_items` for queued and auto-approved candidates that do not already have one
   - snapshot top comments and optional translated comments
   - generate `threads_draft` for high-scoring candidates
   - auto-approved items are stored with `decision=approved` and `reviewed_by=semi-auto`
3. Review action (`/review-items/{id}/decision`)
   - `approved` / `rejected` / `archived`
   - archived items created by `archive-worker` can later be recalled back to `queued`
4. Publish (`/ops/publish/run` or scheduler)
   - schedule approved candidates into `publish_jobs`
   - publish with `review_items.threads_draft` when available, otherwise fallback to raw content
   - write `published_post_records` on success
   - retries and terminal notification on failures
5. Daily summary (`run_daily_summary_cycle` or scheduler)
   - archive pending queued items older than 14 days
   - include `Auto-archived: N` in the Telegram summary
   - include today's high-score archived items in the summary
6. Telegram recall (`/recall`)
   - list high-score items auto-archived by `archive-worker`
   - recall moves candidate status `archived -> queued`
   - reset review decision `archived -> pending`

## 3. Safety rules before reset

- Stop API and worker first.
- Confirm your `.env` points to dedicated resources:
  - dedicated PostgreSQL database (recommended)

Check current runtime target quickly:

```bash
curl http://127.0.0.1:8000/health
```

Look at:
- `database_target`

## 4. Safe reset script (recommended)

Use:
- `scripts/reset_state.py`

It resets this service's known PostgreSQL tables only.
There is no Redis reset path anymore because Redis has been removed from the runtime.

### 4.1 Reset PostgreSQL tables only

```bash
uv run python scripts/reset_state.py --yes
# or simply:
make reset
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

## 6. Validate after reset

1. Recreate schema (idempotent):

```bash
uv run python scripts/migrate.py
```

2. Run one minimal ingestion smoke:

```bash
uv run python scripts/ops_cli.py ingest --time hour --sort top --limit 1
uv run python scripts/ops_cli.py review-list --status pending --limit 10
```

Expected after reset:
- all pipeline tables are empty
- the next ingestion run behaves like a fresh bootstrap for dedup and review queue state
