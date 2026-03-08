## Context

The codebase has two independent issues addressed in one change:

1. **Redis dead code.** `QueueClient` wraps a Redis connection (`redis>=6.4.0` dependency) but only `ping()` is ever called — through health checks in `app.py` and `telegram_routes.py`. The `enqueue()`/`dequeue()` methods have zero callers across the entire codebase. The default `REDIS_URL=memory://queue` means even `ping()` always returns `True` without contacting a server. This adds a misleading "queue" health signal and an unnecessary dependency.

2. **Archive lifecycle gap.** `ArchiveWorker` exists with two methods (`archive_stale_review_items`, `build_high_score_recall`) but is never called from the scheduler or any endpoint. Pending review items therefore accumulate indefinitely. There is no way to expire stale items, no archive-related notifications, and no path to recover high-scoring items after archival (`ARCHIVED` is a terminal state).

### Current daily summary flow

```
scheduler (cron) → run_daily_summary_cycle()
                   → build_stats_payload(session)
                   → telegram_service.format_stats_message(stats)
                   → telegram_client.send_message(...)
```

### Current lifecycle transitions

```
SEEN → SCORED → QUEUED → REVIEWED → APPROVED → SCHEDULED → PUBLISHED
                  ↓          ↓
               ARCHIVED   REJECTED
               ARCHIVED   ARCHIVED
```

`ARCHIVED` and `REJECTED` have no outgoing transitions.

## Goals / Non-Goals

**Goals:**
- Remove all Redis/QueueClient code and the `redis` dependency so that health checks reflect only real infrastructure (database).
- Integrate `ArchiveWorker` into the daily summary cycle so stale pending items are automatically archived before the summary is built.
- Include archive stats (count archived, high-score recalls) in the daily Telegram summary message.
- Provide a `/recall` Telegram command to list and unarchive high-score items that were auto-archived.
- Open the `ARCHIVED → QUEUED` lifecycle transition to enable the recall flow.

**Non-Goals:**
- No new REST API endpoints for archive or recall — this is Telegram-only and scheduler-internal.
- No configurable `max_age_days` via environment variable — hardcoded to 14 days for now.
- No configurable `min_score` for high-score recall — hardcoded to 4.0 for now.
- No recurring recall reminders — `/recall` is on-demand only.
- No archive/recall for manually rejected items — only items archived by `archive-worker` are recallable.

## Decisions

### D1: Remove Redis entirely rather than keep a stub

**Decision**: Delete `queue_client.py`, remove `redis` from `pyproject.toml`, strip `REDIS_URL` from settings and `.env.example`.

**Alternatives considered**:
- *Keep QueueClient as a no-op stub*: Would avoid breaking any downstream references but preserves dead code and a false "queue: healthy" signal. Rejected — there are only 4 call sites and all are straightforward to patch.
- *Replace with a lightweight health-check-only ping*: Adds complexity for no functional gain. Rejected.

**Rationale**: The `extra="ignore"` setting in Pydantic means existing `.env` files with `REDIS_URL` will not error. The only visible impact is that `/health` and Telegram `/health` responses will no longer include a `queue` field.

### D2: Run archive inside `run_daily_summary_cycle`, not as a separate scheduler job

**Decision**: Call `ArchiveWorker.archive_stale_review_items()` at the beginning of `run_daily_summary_cycle()` within the same DB session, before building the stats payload.

**Alternatives considered**:
- *Separate scheduler job*: Would require coordinating timing (archive must finish before summary). Adds complexity and a potential race condition. Rejected.
- *Archive on every ingestion cycle*: Wasteful — stale items only need checking once per day. Rejected.

**Rationale**: Running archive-then-summary in a single function ensures the summary always reflects the post-archive state. This reuses the existing cron schedule (`TELEGRAM_DAILY_SUMMARY_HOUR` / `TELEGRAM_DAILY_SUMMARY_TIMEZONE`) with no new settings.

### D3: Add a new `build_todays_high_score_recall` method rather than reuse `build_high_score_recall`

**Decision**: Add a new method to `ArchiveWorker` that filters archived candidates to only those whose review item was archived by `"archive-worker"` and whose `reviewed_at` falls within the current day (UTC). This prevents the daily summary from repeating historical recalls.

**Alternatives considered**:
- *Reuse existing `build_high_score_recall` with a date filter parameter*: Would change the existing method's signature. Acceptable but less explicit. Rejected in favor of a dedicated method for clarity.

**Rationale**: The existing `build_high_score_recall` returns ALL high-score archived items regardless of when they were archived. For the daily summary, we only want today's newly archived items. A separate method makes intent clear and keeps the existing method available for other use cases (e.g., `/recall` command lists all recallable items).

### D4: Guard recall to archive-worker-archived items only

**Decision**: The `/recall` command and unarchive transition will check `reviewed_by == "archive-worker"` on the review item. Items that were manually rejected or manually archived cannot be recalled via this mechanism.

**Alternatives considered**:
- *Allow recall for any archived item*: Could lead to recalling items that were intentionally rejected by the operator. Rejected.
- *Add a separate `archived_by` field to CandidatePost*: Over-engineering — `reviewed_by` on the ReviewItem already captures this. Rejected.

**Rationale**: The `reviewed_by` field is already set to `"archive-worker"` by `archive_stale_review_items()`. This is a sufficient guard without schema changes.

### D5: Unarchive resets both ReviewItem and CandidatePost

**Decision**: When an item is recalled:
1. Open lifecycle transition: `ARCHIVED → QUEUED` in `_ALLOWED_CANDIDATE_TRANSITIONS`.
2. The recall handler resets `CandidatePost.status` back to `queued`.
3. The recall handler resets `ReviewItem.decision` back to `pending` and clears `reviewed_by` and `reviewed_at`.

This re-enters the item into the review pipeline as if it were freshly queued.

**Alternatives considered**:
- *Create a new CandidatePost + ReviewItem pair*: Loses the original score and metadata. Rejected.
- *Add a new status like `RECALLED`*: Adds lifecycle complexity without clear benefit. Rejected.
- *Only reset CandidatePost, leave ReviewItem archived*: Would break the review flow since the ReviewWorker skips candidates that already have a ReviewItem. Rejected.

**Rationale**: The simplest approach — reuse existing states. The review item retains all its original content (drafts, translations, risk tags) so the operator can review it again without re-running Ollama.

### D6: `/recall` shows all recallable items, not just today's

**Decision**: The `/recall` command lists ALL auto-archived high-score items (`reviewed_by == "archive-worker"` AND `final_score >= 4.0`), not just today's. It uses inline keyboard "Recall" buttons to unarchive individual items.

**Alternatives considered**:
- *Show only today's recalls*: Too limiting — operator might want to browse older auto-archived items. Rejected.
- *Paginate results*: Premature complexity. If the list grows too long, add pagination later. For now, limit to top 10 by score.

**Rationale**: The daily summary already shows today's newly archived high-score items. `/recall` serves a different purpose — browsing the full recallable backlog on demand.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **Redis removal breaks existing deployments** | `extra="ignore"` in Pydantic settings means stale `REDIS_URL` in `.env` is silently ignored. No startup failure. |
| **Archive runs during summary and takes too long** | The query targets a specific subset (pending + queued + old). With SQLite/small datasets this will be sub-second. Add timing logs to detect if it becomes slow. |
| **Recalled item gets re-archived next day** | After recall, the item's `reviewed_at` is cleared and it re-enters as `pending/queued`. The archive query filters on `captured_at < 14 days ago`, so if `captured_at` is still old, it could be re-archived. Mitigation: the operator should review recalled items within 24 hours, which is reasonable since they actively chose to recall them. Alternatively, the archive query could also check that `reviewed_at` is NULL or older than the cutoff, but this adds complexity. Accept the risk for now. |
| **`ARCHIVED → QUEUED` transition could be misused** | The transition exists in the lifecycle map but is only triggered from the `/recall` handler, which checks `reviewed_by == "archive-worker"`. No API endpoint exposes unarchive directly. |

## Open Questions

- None — all decisions have been resolved through the explore-mode discussion.
