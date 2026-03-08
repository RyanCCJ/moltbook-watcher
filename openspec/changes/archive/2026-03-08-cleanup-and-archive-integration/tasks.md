## 1. Remove Redis / QueueClient Dead Code

- [x] 1.1 Delete `src/services/queue_client.py`
- [x] 1.2 Remove `redis` from `pyproject.toml` dependencies and run `uv lock`
- [x] 1.3 Remove `redis_url` field from `Settings` in `src/config/settings.py`
- [x] 1.4 Remove `REDIS_URL` entry from `.env.example`
- [x] 1.5 Remove QueueClient import, startup (`connect`), shutdown (`close`), and health-check (`ping`) from `src/api/app.py`; remove the `queue` field from the `/health` response and the `redis_target` field; delete the `_format_redis_target` helper
- [x] 1.6 Remove QueueClient import and usage from `src/api/telegram_routes.py` `/health` command handler; update `health_data` dict to drop the `queue` key
- [x] 1.7 Update `TelegramService.format_health_message` in `src/services/telegram_service.py` to remove the queue status line
- [x] 1.8 Remove or update any tests referencing `QueueClient` or `redis_url` (search `tests/` for `queue_client`, `QueueClient`, `redis`)

## 2. Lifecycle Transition: ARCHIVED → QUEUED

- [x] 2.1 In `src/models/lifecycle.py`, update `_ALLOWED_CANDIDATE_TRANSITIONS` to add `CandidateStatus.QUEUED` to the `ARCHIVED` transition set
- [x] 2.2 Add unit test validating `can_transition_candidate(ARCHIVED, QUEUED)` returns `True`
- [x] 2.3 Add unit test validating other transitions from `ARCHIVED` (e.g., `ARCHIVED → APPROVED`) still raise `ValueError`

## 3. ArchiveWorker Enhancements

- [x] 3.1 Add `build_todays_high_score_recall` method to `ArchiveWorker` in `src/workers/archive_worker.py`: query archived candidates where `ReviewItem.reviewed_by == "archive-worker"` AND `ReviewItem.reviewed_at >= start_of_today (UTC)` AND `ScoreCard.final_score >= 4.0`, ordered by `final_score` desc
- [x] 3.2 Add `recall_item` method to `ArchiveWorker`: given a `review_item_id`, verify `reviewed_by == "archive-worker"`, then reset `ReviewItem.decision` to `"pending"`, clear `reviewed_by` and `reviewed_at`, and transition `CandidatePost.status` from `ARCHIVED` to `QUEUED`
- [x] 3.3 Add unit tests for `archive_stale_review_items` (existing method, currently untested)
- [x] 3.4 Add unit tests for `build_todays_high_score_recall`
- [x] 3.5 Add unit tests for `recall_item` — success case, already-recalled case, and non-archive-worker guard

## 4. Integrate Archive into Daily Summary Cycle

- [x] 4.1 In `src/workers/scheduler.py`, update `run_daily_summary_cycle` to instantiate `ArchiveWorker`, call `archive_stale_review_items(session)` and `build_todays_high_score_recall(session)` in a DB session, commit, then pass archive metrics to the summary builder
- [x] 4.2 Update `build_stats_payload` in `src/services/telegram_reporting.py` to accept and include `archived_count` and `high_score_recalls` list in the returned stats dict
- [x] 4.3 Update `TelegramService.format_stats_message` in `src/services/telegram_service.py` to render archive stats: "Auto-archived: N" line, and list high-score recall items (source URL + score) when present
- [x] 4.4 Add integration test verifying that `run_daily_summary_cycle` archives stale items and includes archive stats in the summary message

## 5. /recall Telegram Command

- [x] 5.1 Add `/recall` command handler in `src/api/telegram_routes.py`: instantiate `ArchiveWorker`, call `build_high_score_recall(session, min_score=4.0)` filtered to `reviewed_by == "archive-worker"`, format results, and send with inline "Recall" buttons (callback data: `recall:<review_item_id>`)
- [x] 5.2 Add recall message formatting methods to `TelegramService` in `src/services/telegram_service.py`: `format_recall_list(items)` for the list view and `build_recall_inline_keyboard(review_item_id)` for inline buttons
- [x] 5.3 Add `recall` callback handler in `_handle_callback_query` in `src/api/telegram_routes.py`: parse `recall:<review_item_id>`, call `ArchiveWorker.recall_item`, handle success/already-recalled/not-eligible responses, and reply via `answer_callback_query`
- [x] 5.4 Update `/help` response in `TelegramService.format_help_message` to include `/recall` command description
- [x] 5.5 Add contract test for `/recall` command (no recallable items, with recallable items)
- [x] 5.6 Add contract test for recall callback (successful recall, already recalled, not eligible)
