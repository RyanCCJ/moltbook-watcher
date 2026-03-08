# Moltbook Watcher

Moltbook-to-Threads curation service (FastAPI + worker).

Current pipeline:
- Fetch posts from Moltbook
- Fetch top comments for each post
- Deduplicate and score with Ollama
- Archive low-score posts immediately after scoring
- Build a review queue only for posts that meet the review threshold
- Auto-approve fast-track posts when `PUBLISH_MODE=semi-auto`
- Send one Telegram ingestion digest per cycle instead of per-item push notifications
- Auto-archive stale queued items before the daily Telegram summary
- Let operators recall high-score auto-archived items from Telegram with `/recall`
- Let operators approve/reject before publishing
- Ingestion and review run in separate DB transactions (review failure does not roll back ingested candidates)

## Quick Start

### 1) Install

```bash
uv sync --extra dev
cp .env.example .env
```

Recommended minimal local mode:

```env
DATABASE_URL=sqlite+aiosqlite:///./moltbook.db
MOLTBOOK_API_BASE_URL=https://www.moltbook.com/api/v1
MOLTBOOK_API_TOKEN=<your_token>
TRANSLATION_LANGUAGE=
THREADS_LANGUAGE=en
```

Language behavior:
- `TRANSLATION_LANGUAGE` default is empty, so translation is skipped.
- Set `TRANSLATION_LANGUAGE=zh-TW` to restore previous always-translate-to-Chinese behavior.
- `THREADS_LANGUAGE` controls the generated Threads draft language independently (default `en`).
- `INGESTION_TIME`, `INGESTION_LIMIT`, and `INGESTION_SORT` control the default ingestion window.
- `REVIEW_MIN_SCORE` controls which posts enter review (default `3.5`).
- `AUTO_PUBLISH_MIN_SCORE` controls fast-track eligibility for `PUBLISH_MODE=semi-auto` (default `4.0`).

### 2) Initialize DB

```bash
uv run python scripts/migrate.py
```

### 3) Run services

```bash
make api
make worker
```

## Common Commands

```bash
uv run python scripts/ops_cli.py health
uv run python scripts/ops_cli.py ingest --time hour --sort top --limit 1 --timeout 300
uv run python scripts/ops_cli.py review-list --status pending --limit 10
uv run python scripts/ops_cli.py review-decide <REVIEW_ITEM_ID> --decision approved --reviewed-by operator
uv run python scripts/ops_cli.py publish-run
uv run python scripts/ops_cli.py publish-jobs
make reset
```

Show parameter choices:

```bash
uv run python scripts/ops_cli.py ingest --help
```

## Local API Endpoints

- `POST /ops/ingestion/run?time=<...>&sort=<...>&limit=<...>`
- Defaults for ingestion come from `INGESTION_TIME`, `INGESTION_LIMIT`, and `INGESTION_SORT`.
- `GET /review-items?status=pending&limit=10`
- `POST /review-items/{id}/decision`
- `POST /ops/publish/run`
- `GET /publish-jobs`

## Test

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

## Verify

- API health: `curl http://127.0.0.1:8000/health`
- Ingest once: `uv run python scripts/ops_cli.py ingest --time hour --sort top --limit 1`
- Review queue: `uv run python scripts/ops_cli.py review-list --status pending --limit 10`
- Telegram flow: send `/health`, `/pending`, `/help`, `/stats`, and `/recall`
- Archive/recall flow: see `docs/service-setup-run-test.md`

## Troubleshooting

- Ingest timeout:
  - Increase timeout (for example `--timeout 300`)
  - Confirm both API and worker are running
- `window=month` returns mostly recent posts:
  - Expected with bounded scanning (safe sampling)
  - Try `--sort new` or run multiple cycles
- `persisted_count=0`:
  - Usually dedup filtered existing content
  - Run `make reset` for clean smoke tests
  - `make reset` now resets database tables only; Redis is no longer part of the runtime
- No pending review item after ingestion:
  - Check whether the post scored below `REVIEW_MIN_SCORE`
  - Low-score posts now go directly to `archived`

## Additional Docs

- `docs/service-setup-run-test.md`
- `docs/data-flow-and-safe-reset.md`
- `docs/ollama-and-threads-credentials.md`
