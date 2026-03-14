## Why

The codebase contains dead infrastructure (Redis/QueueClient) that adds unnecessary dependencies and confusing health-check signals, while a fully implemented ArchiveWorker sits unused. Pending review items accumulate indefinitely with no automatic cleanup, and high-scoring items that time out are silently lost. This change removes the dead code and activates the archive lifecycle — including daily auto-archive before the Telegram summary, high-score recall notifications, and a `/recall` command to unarchive worthy items.

## What Changes

- **Remove Redis/QueueClient dead code**: Delete `src/services/queue_client.py`, remove the `redis` dependency from `pyproject.toml`, strip `REDIS_URL` from `.env.example` and `src/config/settings.py`, and remove all QueueClient references from `src/api/app.py`, `src/api/telegram_routes.py`, and health-check responses.
- **Integrate ArchiveWorker into daily summary cycle**: Run `archive_stale_review_items(max_age_days=14)` before building the daily summary stats, so the Telegram summary reflects the post-archive state.
- **Add archive stats to daily summary notification**: Include the count of auto-archived items and any high-score recalls (newly archived items with `final_score >= 4.0`) in the daily Telegram summary message.
- **Add `/recall` Telegram command**: Allow the operator to view and unarchive high-score items that were auto-archived. Shows a list of recently archived high-score candidates with inline "Recall" buttons.
- **Add unarchive lifecycle transition**: Open a new transition `ARCHIVED → QUEUED` to allow recalled items to re-enter the review pipeline. Guard this transition so only items archived by the archive-worker (not manually rejected) can be recalled.

## Capabilities

### New Capabilities
- `archive-integration`: Daily automatic archival of stale pending review items before the Telegram summary, with archive stats included in the daily notification. High-score recall list for newly archived items.
- `recall-command`: Telegram `/recall` command that lists recently auto-archived high-score items and provides inline keyboard buttons to unarchive (recall) them back into the review queue.

### Modified Capabilities
- `telegram-commands`: Add `/recall` to the set of recognized bot commands and update the `/help` response to include it.

## Impact

- **Removed files**: `src/services/queue_client.py`
- **Removed dependency**: `redis` package from `pyproject.toml`
- **Modified files**: `src/config/settings.py` (remove `redis_url`), `.env.example` (remove `REDIS_URL`), `src/api/app.py` (remove QueueClient startup/shutdown/health), `src/api/telegram_routes.py` (remove QueueClient health-check usage, add `/recall` handler), `src/services/telegram_service.py` (add recall message formatting), `src/services/telegram_reporting.py` (add archive stats to summary payload), `src/workers/scheduler.py` (add archive step to daily summary cycle), `src/workers/archive_worker.py` (add method for today-only high-score recall), `src/models/lifecycle.py` (add `ARCHIVED → QUEUED` transition)
- **Tests**: Update or remove tests referencing QueueClient; add tests for archive integration, recall command, and unarchive transition
- **APIs**: No new REST endpoints; changes are internal (scheduler) and Telegram-only (`/recall`)
- **Breaking**: **BREAKING** — `REDIS_URL` environment variable is removed. Deployments referencing it will see a harmless ignored variable (due to `extra="ignore"` in Settings), but it should be cleaned up.
