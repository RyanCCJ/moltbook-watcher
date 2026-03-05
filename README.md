# Moltbook Watcher

Moltbook-to-Threads curation service (FastAPI + worker).

Current pipeline:
- Fetch posts from Moltbook
- Fetch top comments for each post
- Deduplicate and score with Ollama
- Build a review queue
- Let operators approve/reject before publishing

## Quick Start

### 1) Install

```bash
uv sync --extra dev
cp .env.example .env
```

Recommended minimal local mode:

```env
DATABASE_URL=sqlite+aiosqlite:///./moltbook.db
REDIS_URL=memory://queue
MOLTBOOK_API_BASE_URL=https://www.moltbook.com/api/v1
MOLTBOOK_API_TOKEN=<your_token>
TRANSLATION_LANGUAGE=
THREADS_LANGUAGE=en
```

Language behavior:
- `TRANSLATION_LANGUAGE` default is empty, so translation is skipped.
- Set `TRANSLATION_LANGUAGE=zh-TW` to restore previous always-translate-to-Chinese behavior.
- `THREADS_LANGUAGE` controls the generated Threads draft language independently (default `en`).

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
uv run python scripts/ops_cli.py ingest --window past_hour --sort top --limit 1 --timeout 300
uv run python scripts/ops_cli.py review-list --status pending --limit 10
uv run python scripts/ops_cli.py review-decide <REVIEW_ITEM_ID> --decision approved --reviewed-by operator
uv run python scripts/ops_cli.py publish-run
uv run python scripts/ops_cli.py publish-jobs
```

Show parameter choices:

```bash
uv run python scripts/ops_cli.py ingest --help
```

## Local API Endpoints

- `POST /ops/ingestion/run?window=<...>&sort=<...>&limit=<...>`
- `GET /review-items?status=pending&limit=10`
- `POST /review-items/{id}/decision`
- `POST /ops/publish/run`
- `GET /publish-jobs`

## Test

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

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

## Additional Docs

- `docs/service-setup-run-test.md`
- `docs/data-flow-and-safe-reset.md`
- `docs/ollama-and-threads-credentials.md`
