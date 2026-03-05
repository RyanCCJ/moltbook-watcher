# Moltbook Watcher: Setup, Run, and Test Guide

This guide explains how to configure, start, and test the service locally.

For Ollama startup/config and Threads credential setup, see:
- `docs/ollama-and-threads-credentials.md`
- `docs/systemd-launchd-runbook.md`

## 1. Prerequisites

- macOS/Linux terminal
- `uv` installed
- Python 3.12+ available to `uv`

Optional for full runtime mode:
- PostgreSQL
- Redis

## 2. Install Dependencies

From repository root:

```bash
uv sync --extra dev
```

## 3. Configure Environment

Create your local env file:

```bash
cp .env.example .env
```

Update values in `.env` as needed.

After changing `.env`, fully restart running API/worker processes.
`uvicorn --reload` does not automatically reload only because `.env` changed.

Important:
- `.env.example` is configured for PostgreSQL + Redis.
- If you do not run PostgreSQL/Redis locally, switch to minimal values:

```env
DATABASE_URL=sqlite+aiosqlite:///./moltbook.db
REDIS_URL=memory://queue
```

Important variables:
- `DATABASE_URL`
- `REDIS_URL`
- `MOLTBOOK_API_BASE_URL`
- `MOLTBOOK_API_TOKEN`
- `TRANSLATION_LANGUAGE` (empty by default, skips translation)
- `THREADS_LANGUAGE` (default `en`, controls generated Threads draft language)
- `THREADS_API_BASE_URL`
- `THREADS_API_TOKEN`
- `THREADS_ACCOUNT_ID`
- `SMTP_*`

Moltbook API configuration (from the local `moltbook` skill):
- Use `https://www.moltbook.com/api/v1` as base URL
- Send key as `Authorization: Bearer <MOLTBOOK_API_TOKEN>`
- Never send Moltbook API key to non-`www.moltbook.com` domains

Recommended `.env` values:

```env
MOLTBOOK_API_BASE_URL=https://www.moltbook.com/api/v1
MOLTBOOK_API_TOKEN=<moltbook_api_key>
```

How to get `MOLTBOOK_API_TOKEN`:
- Register an agent (returns `api_key`, `claim_url`, `verification_code`):

```bash
curl -X POST https://www.moltbook.com/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"name":"YourAgentName","description":"What you do"}'
```

- Store the returned `api_key` securely and set it as `MOLTBOOK_API_TOKEN`.

## 4. Choose Runtime Mode

### A. Minimal local mode (quick start)

Use defaults from `src/config/settings.py`:
- SQLite: `sqlite+aiosqlite:///./moltbook.db`
- In-memory queue: `memory://queue`

This is the fastest way to run API and tests locally.

### B. Full integration mode

Use `.env.example` values and run PostgreSQL + Redis locally, then keep:
- `DATABASE_URL=postgresql+asyncpg://...`
- `REDIS_URL=redis://...`

### C. Shared Kubernetes PostgreSQL with dedicated `moltbook` account

If you are reusing an existing PostgreSQL service in Kubernetes, create a
dedicated user/database for this project.

1. Export your desired app credentials:

```bash
export MOLTBOOK_DB_USER="moltbook_user"
export MOLTBOOK_DB_PASSWORD="password"
export MOLTBOOK_DB_NAME="moltbook"
```

2. Create role + database (run once, idempotent):

```bash
kubectl -n default exec -i postgres-0 -- psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -v app_user="$MOLTBOOK_DB_USER" \
  -v app_pass="$MOLTBOOK_DB_PASSWORD" \
  -v app_db="$MOLTBOOK_DB_NAME" <<'SQL'
SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db') \gexec
SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'app_db', :'app_user') \gexec
SQL
```

3. Update `.env`:

```env
DATABASE_URL=postgresql+asyncpg://moltbook_user:password@<POSTGRES_SERVICE_IP>:5432/moltbook
REDIS_URL=redis://<REDIS_SERVICE_IP>:6379/0
```

4. Restart API/worker so new `.env` is applied.

## 5. Initialize Database Schema

```bash
uv run python scripts/migrate.py
```

## 6. Start the Service

Open two terminals at repo root.

Terminal 1 (API):

```bash
make api
```

Terminal 2 (scheduler/worker):

```bash
make worker
```

## 7. Verify Health

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/live
```

Expected:
- `/health/live` returns `{"status":"ok"}`
- `/health` returns `status: ok` when DB and queue are reachable

## 8. User Story Smoke Test (US1 -> US2 -> US3)

Use these API calls to validate end-to-end behavior with real runtime wiring.

### 8.1 US1: discovery + scoring + dedup

Run one small ingestion cycle first (`limit=1`):

```bash
curl -X POST "http://127.0.0.1:8000/ops/ingestion/run?window=past_hour&sort=top&limit=1"
```

Expected:
- `metrics.fetched_count >= 1`
- `metrics.persisted_count >= 1` (on fresh data)
- `metrics.review_items_created >= 1`

If `persisted_count` is `0`, it usually means fetched content was deduplicated.

### 8.2 US2: review queue and decision

List review queue:

```bash
curl "http://127.0.0.1:8000/review-items?status=pending&limit=10"
```

Pick one `id` from response, then approve it:

```bash
curl -X POST "http://127.0.0.1:8000/review-items/<REVIEW_ITEM_ID>/decision" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approved","reviewedBy":"operator"}'
```

Expected:
- response contains `reviewItemId`, `decision=approved`, `decidedAt`
- approved candidate enters publish scheduling pipeline

### 8.3 US3: publish scheduling + execution

Run one publish cycle:

```bash
curl -X POST "http://127.0.0.1:8000/ops/publish/run"
```

Check jobs:

```bash
curl "http://127.0.0.1:8000/publish-jobs"
```

Expected:
- approved candidates are scheduled and processed
- job status advances (`scheduled` -> `in_progress` -> `published` or retry/failure states)

### 8.4 Faster operation via CLI script

If you do not want to type raw API calls, use:

```bash
uv run python scripts/ops_cli.py --help
```

Common commands:

```bash
uv run python scripts/ops_cli.py health
uv run python scripts/ops_cli.py ingest --window past_hour --sort top --limit 1
uv run python scripts/ops_cli.py review-list --status pending --limit 10
uv run python scripts/ops_cli.py review-decide <REVIEW_ITEM_ID> --decision approved --reviewed-by operator
uv run python scripts/ops_cli.py publish-run
uv run python scripts/ops_cli.py publish-jobs
```

One-shot smoke (ingest -> approve first pending -> publish):

```bash
uv run python scripts/ops_cli.py smoke --approve --limit 1
```

## 9. Run Tests

Run all tests:

```bash
uv run --extra dev pytest
```

Run lint:

```bash
uv run --extra dev ruff check .
```

Run key suites separately:

```bash
uv run --extra dev pytest tests/contract
uv run --extra dev pytest tests/integration
uv run --extra dev pytest tests/unit
```

## 10. Useful Endpoints

- `GET /health`
- `GET /health/live`
- `POST /ops/ingestion/run` (supports `window`, `sort`, `limit`)
- `POST /ops/publish/run`
- `GET /review-items`
- `POST /review-items/{reviewItemId}/decision`
- `PUT /publishing/mode`
- `POST /publishing/pause`
- `GET /publish-jobs`

## 11. Troubleshooting

- `database/queue degraded` in `/health`:
  - Verify `DATABASE_URL` and `REDIS_URL`
  - Confirm PostgreSQL/Redis are running (full mode)
- `persisted_count=0` after ingestion:
  - Data may be deduplicated against existing `candidate_posts`
  - Retry with a different `window`/`sort` or a fresh DB for smoke testing
  - Ingestion uses API `sort` and applies local time-window filtering to avoid large upstream fetches
- Publish flow appears inactive:
  - Check if publishing was paused via `POST /publishing/pause`
- FastAPI deprecation warnings about `on_event`:
  - Non-blocking for now; migration to lifespan handlers is a future cleanup
