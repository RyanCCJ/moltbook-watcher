## Why

During batch ingestion of 100 posts, a single httpx timeout (180s) in `_generate_threads_draft` triggers the circuit breaker (`self._ollama_enabled = False`), permanently disabling all subsequent Ollama calls for the remainder of the batch. This results in 68 out of 75 review items being created with empty translations and empty Threads drafts. The current circuit breaker treats a single transient timeout identically to "Ollama is completely down," and the system provides no mechanism to recover — there is no way to regenerate empty review items without re-ingesting from scratch.

Additionally, the Ollama timeout (180s) is hardcoded and cannot be tuned without code changes. The `think=True` mode used for Threads draft generation can regularly exceed 180s on smaller models (e.g., `qwen3.5:4b`), especially with longer posts and comments.

## What Changes

- **Smarten the circuit breaker**: Replace the single-failure-disables-all pattern with a consecutive-failure counter. Ollama is only disabled after N consecutive failures (default: 3), and the counter resets on any successful call. This applies uniformly to `_generate_threads_draft`, `_translate_batch`, and `_translate`.
- **Make Ollama timeout configurable**: Introduce an `OLLAMA_TIMEOUT_SECONDS` environment variable (default: 300) to control the httpx client timeout for `ReviewPayloadService`, removing the hardcoded 180s.
- **Add `/regenerate` Telegram command**: A new command that re-runs Phase 2 (translation + Threads draft generation) for review items that have empty content. `/regenerate` with no arguments processes all pending review items with empty translations or empty Threads drafts. `/regenerate <N>` targets a specific item from the current `/pending` list.
- **Add regenerate REST API endpoint**: Expose `POST /ops/regenerate` (with optional `review_item_id` query param) so regeneration can be triggered without Telegram. This follows the existing pattern where every Telegram command has a corresponding REST endpoint in `ops_routes.py`.
- **Add `regenerate` CLI subcommand**: Add a `regenerate` subcommand to `scripts/ops_cli.py` that calls the new REST endpoint, so that all pipeline operations can be performed from the terminal without Telegram configured.
- **Add Makefile target**: Add `ops-regenerate` target to the Makefile for convenient access.
- **Update documentation**: Update `docs/service-setup-run-test.md` to document the new `regenerate` CLI command, REST endpoint, and `OLLAMA_TIMEOUT_SECONDS` setting. Update the troubleshooting section with guidance on empty translations/drafts recovery.

## Capabilities

### New Capabilities
- `regenerate-command`: Regenerate (re-run Phase 2: translation + Threads draft) for review items with empty content. Accessible via Telegram `/regenerate`, REST API `POST /ops/regenerate`, and CLI `ops_cli.py regenerate`. `/regenerate` with no arguments processes all pending items with empty content; `/regenerate <N>` targets a specific item from the pending list.

### Modified Capabilities
- `threads-draft-gen`: Update the failure handling requirement — replace "disables Ollama on httpx error" with the consecutive-failure circuit breaker pattern. Add configurable timeout requirement via `OLLAMA_TIMEOUT_SECONDS`.
- `batch-translation`: Update the failure handling requirement — align the circuit breaker behavior with the same consecutive-failure pattern used in threads-draft-gen.
- `telegram-commands`: Add the `/regenerate` command to the command list and `/help` output.

## Impact

- **`src/services/review_payload_service.py`**: Circuit breaker logic changes in three exception handlers (`_generate_threads_draft`, `_translate_batch`, `_translate`). Constructor accepts new timeout parameter from settings.
- **`src/config/settings.py`**: New `ollama_timeout_seconds` setting (default: 300).
- **`src/workers/runtime.py`**: Pass configurable timeout to `ReviewPayloadService` and `ScoringService`. Extract regeneration logic into a reusable `run_regenerate_once()` function.
- **`src/api/ops_routes.py`**: New `POST /ops/regenerate` endpoint.
- **`src/api/telegram_routes.py`**: New `/regenerate` command handler that calls the shared regeneration logic.
- **`src/services/telegram_service.py`**: Help message update, regenerate result formatting.
- **`src/models/review_item.py`**: New repository method to bulk-update translation and threads_draft fields.
- **`src/workers/review_worker.py`**: Extracted regeneration logic that can be reused by both the Telegram command and the REST endpoint.
- **`scripts/ops_cli.py`**: New `regenerate` subcommand.
- **`Makefile`**: New `ops-regenerate` target.
- **`.env.example`**: Document `OLLAMA_TIMEOUT_SECONDS`.
- **`docs/service-setup-run-test.md`**: Document regenerate workflow (CLI + REST), `OLLAMA_TIMEOUT_SECONDS`, and troubleshooting for empty translations/drafts.
- **Existing tests**: Tests covering circuit breaker behavior in `review_payload_service` will need updates.
