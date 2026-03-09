## 1. Configurable Timeout

- [x] 1.1 Add `ollama_timeout_seconds: float = Field(default=300, ge=30)` to `Settings` in `src/config/settings.py`
- [x] 1.2 Add `OLLAMA_TIMEOUT_SECONDS` with description to `.env.example` under the AI Services section
- [x] 1.3 Pass `settings.ollama_timeout_seconds` to `ReviewPayloadService` constructor in `src/workers/runtime.py`
- [x] 1.4 Pass `settings.ollama_timeout_seconds` to `ScoringService` constructor in `src/workers/runtime.py`
- [x] 1.5 Update unit tests for Settings validation (reject values below 30)

## 2. Consecutive-Failure Circuit Breaker

- [x] 2.1 Add `_consecutive_failures: int` and `_max_consecutive_failures: int` fields to `ReviewPayloadService.__init__`
- [x] 2.2 Add `_record_ollama_success()` helper that resets `_consecutive_failures = 0`; call it after successful response in `_chat_with_think_fallback`
- [x] 2.3 Add `_record_ollama_failure()` helper that increments counter and disables Ollama when threshold is reached
- [x] 2.4 Replace `self._ollama_enabled = False` in `_generate_threads_draft` exception handler with call to `_record_ollama_failure()`; keep non-HTTP errors (empty response, near-copy) out of the counter
- [x] 2.5 Replace `self._ollama_enabled = False` in `_translate_batch` exception handler with call to `_record_ollama_failure()`; ensure `ValueError` (JSON parse / missing keys) does NOT increment the counter
- [x] 2.6 Replace `self._ollama_enabled = False` in `_translate` exception handler with call to `_record_ollama_failure()`
- [x] 2.7 Update existing unit tests for circuit breaker behavior: verify single failure does not disable, 3 consecutive failures disable, success resets counter, non-HTTP errors do not count

## 3. ReviewItemRepository.update_payload

- [x] 3.1 Add `update_payload(self, session, *, review_item_id, chinese_translation_full, top_comments_translated, threads_draft)` method to `ReviewItemRepository` in `src/models/review_item.py`
- [x] 3.2 Method SHALL require the review item to be in `pending` decision state; raise `ValueError("Decision already submitted")` otherwise
- [x] 3.3 Add unit tests for `update_payload` (success, non-pending rejection)

## 4. Regeneration Logic

- [x] 4.1 Add `regenerate_items(self, session, items)` method to `ReviewWorker` in `src/workers/review_worker.py` that re-runs `build_payload` and calls `update_payload` for each item
- [x] 4.2 Add `run_regenerate_once(review_item_id: str | None = None)` function in `src/workers/runtime.py` that creates a fresh `ReviewPayloadService`, finds empty items (or a specific item), and calls `ReviewWorker.regenerate_items`
- [x] 4.3 Return metrics dict with `regenerated_count`, `skipped_count`, `failed_count`
- [x] 4.4 Add unit tests for `regenerate_items` (regenerates empty items, skips items with content in batch mode, handles Ollama failure gracefully)

## 5. REST API Endpoint

- [x] 5.1 Add `POST /ops/regenerate` endpoint in `src/api/ops_routes.py` with optional `review_item_id` query parameter
- [x] 5.2 Call `run_regenerate_once()` and return `{"ok": true, "metrics": {...}}`
- [x] 5.3 Return HTTP 404 when `review_item_id` is provided but not found
- [x] 5.4 Add integration test for the endpoint

## 6. Telegram Command

- [x] 6.1 Add `/regenerate` command handler in `src/api/telegram_routes.py` — parse optional numeric argument
- [x] 6.2 Validate index against current pending list; reply with usage error if invalid
- [x] 6.3 Reply "No items need regeneration." when no empty items found (batch mode)
- [x] 6.4 Run regeneration as background `asyncio.Task` (same pattern as `/ingest`)
- [x] 6.5 Send follow-up message with regenerated/skipped/failed counts on completion
- [x] 6.6 Update `/help` command output in `src/services/telegram_service.py` to include `/regenerate [number]`
- [x] 6.7 Add unit tests for the Telegram command handler

## 7. CLI and Makefile

- [x] 7.1 Add `regenerate` subcommand to `scripts/ops_cli.py` with optional `--id <review_item_id>` argument
- [x] 7.2 CLI calls `POST /ops/regenerate` (with optional `review_item_id` query param) and prints result JSON
- [x] 7.3 Add `ops-regenerate` target to `Makefile`
- [x] 7.4 Update `.PHONY` line in `Makefile` to include `ops-regenerate`

## 8. Documentation

- [x] 8.1 Add `OLLAMA_TIMEOUT_SECONDS` to the important variables section in `docs/service-setup-run-test.md`
- [x] 8.2 Add `regenerate` to the CLI commands section in `docs/service-setup-run-test.md`
- [x] 8.3 Add `POST /ops/regenerate` to the useful endpoints section in `docs/service-setup-run-test.md`
- [x] 8.4 Add troubleshooting entry for "empty translations and Threads drafts after ingestion" in `docs/service-setup-run-test.md`
