## Context

The `ReviewPayloadService` handles Ollama-based translation and Threads draft generation during Phase 2 of the ingestion pipeline. It uses an instance-level `_ollama_enabled` flag that acts as a circuit breaker — any single `httpx.HTTPError` (including timeout) permanently disables Ollama for the remainder of the batch. This was designed to prevent hours of wasted timeout waiting when Ollama is truly down, but it is too aggressive: a single transient timeout (e.g., a long `think=True` inference) disables Ollama for all subsequent items.

The current system processes review items sequentially in a single for-loop with no recovery path. If items end up with empty translations or drafts, the only option is to re-ingest from scratch.

Key files:
- `src/services/review_payload_service.py` — circuit breaker logic in three handlers
- `src/workers/review_worker.py` — sequential Phase 2 processing loop
- `src/workers/runtime.py` — orchestrates ingestion → review → Telegram notification
- `src/api/ops_routes.py` — REST endpoints for pipeline operations
- `scripts/ops_cli.py` — CLI wrapper for REST endpoints
- `src/api/telegram_routes.py` — Telegram command handlers

## Goals / Non-Goals

**Goals:**
- Prevent a single Ollama timeout from disabling all subsequent translation and draft generation in the same batch
- Allow the Ollama timeout to be tuned via environment variable without code changes
- Provide a way to regenerate empty translations and drafts for existing review items (via Telegram, REST API, and CLI)
- Maintain the terminal-first development pattern: every Telegram command has a corresponding REST endpoint and CLI subcommand

**Non-Goals:**
- Full job queue / async task infrastructure (e.g., Celery, arq) — the current sequential model is adequate for typical batch sizes (≤ 20 items per scheduled cycle)
- Parallel Ollama processing — the local GPU is the bottleneck, parallelism would not improve throughput
- Automatic retry of failed Ollama calls — timeout retry is unlikely to succeed with the same timeout; the fix is a higher timeout or the regenerate mechanism
- Changing the `ScoringService` circuit breaker — scoring uses a separate 60s timeout and a simpler model call; it has not exhibited this problem

## Decisions

### 1. Consecutive-failure circuit breaker (over single-failure or no breaker)

Replace `self._ollama_enabled = False` on first `httpx.HTTPError` with a consecutive-failure counter:

```
success → reset counter to 0
failure → increment counter
counter >= threshold (default: 3) → disable Ollama
```

**Why not remove the breaker entirely?**
If Ollama is genuinely down (crash, OOM), removing the breaker means every item waits the full timeout before failing — for 75 items at 300s each, that is 6+ hours of pointless waiting. The breaker is valuable; it just needs a higher activation threshold.

**Why not per-request retry?**
Timeout retries are unlikely to succeed because the same long-running inference will timeout again. The correct recovery path is the `/regenerate` command after the batch completes (possibly with a larger timeout or after Ollama stabilizes).

**Implementation approach:**
- Add `_consecutive_failures: int = 0` and `_max_consecutive_failures: int = 3` to `ReviewPayloadService.__init__`
- On success in `_chat_with_think_fallback`: reset `_consecutive_failures = 0`
- On `httpx.HTTPError` in the three exception handlers: increment counter; disable only when threshold is reached
- Non-HTTP errors (e.g., JSON parse failures) do NOT count toward the breaker — they indicate model output issues, not connectivity problems

### 2. Configurable timeout via `OLLAMA_TIMEOUT_SECONDS` (default: 300)

**Why 300 instead of 180?**
The `think=True` mode combined with `qwen3.5:4b` and longer post + comments regularly needs 180-240s. 300s provides headroom. Users running faster models can lower it.

**Why a single setting shared by `ReviewPayloadService` and `ScoringService`?**
Separate timeouts per service adds configuration complexity with minimal benefit. One setting covers both. `ScoringService` uses simpler prompts and will rarely approach the limit.

**Implementation:**
- Add `ollama_timeout_seconds: float = Field(default=300, ge=30)` to `Settings`
- Pass to both `ReviewPayloadService` and `ScoringService` constructors in `runtime.py`

### 3. Regeneration via shared `run_regenerate_once()` function

**Architecture:**

```
┌── Telegram ──────────────┐  ┌── REST API ──────────────┐  ┌── CLI ─────────────────┐
│ /regenerate              │  │ POST /ops/regenerate     │  │ ops_cli.py regenerate  │
│ /regenerate <N>          │  │ ?review_item_id=<id>     │  │ --id <id>              │
└──────────┬───────────────┘  └──────────┬───────────────┘  └──────────┬─────────────┘
           │                             │                             │
           └─────────────────┬───────────┘                             │
                             ▼                                         │
                  run_regenerate_once(review_item_id?)    ◀────────────┘
                             │                             (via HTTP)
                             ▼
                  ReviewWorker.regenerate_items(session, items)
                             │
                             ▼
                  ReviewPayloadService.build_payload()
                             │
                  ┌──────────┴──────────┐
                  ▼                     ▼
          _translate_batch()    _generate_threads_draft()
```

**Why a shared function in `runtime.py`?**
This follows the existing pattern: `run_ingestion_once()` and `run_publish_once()` live in `runtime.py` and are called by both Telegram handlers and REST endpoints. The CLI calls the REST endpoint via HTTP.

**Regeneration scope:**
- `/regenerate` (no args): Find all pending review items where `chinese_translation_full = ''` OR `threads_draft = ''`, regenerate them sequentially
- `/regenerate <N>`: Target the Nth item from the current `/pending` list
- REST `POST /ops/regenerate`: Optional `review_item_id` query param; omit to regenerate all empty
- The function creates a fresh `ReviewPayloadService` instance (new `_ollama_enabled = True`, counter reset) so past failures don't carry over

**What gets updated:**
- `ReviewItem.chinese_translation_full`
- `ReviewItem.top_comments_translated`
- `ReviewItem.threads_draft`
- A new `ReviewItemRepository.update_payload()` method handles the bulk update

### 4. Telegram command runs as background task

Following the `/ingest` pattern:
1. Immediately reply: "Regeneration started… (N items)"
2. Run `run_regenerate_once()` as a background `asyncio.Task`
3. Send follow-up message with results on completion

This prevents the Telegram webhook from timing out on large batches.

### 5. Documentation and CLI parity

Every Telegram command must have a corresponding path for terminal-only development:

| Telegram | REST API | CLI | Makefile |
|---|---|---|---|
| `/ingest` | `POST /ops/ingestion/run` | `ops_cli.py ingest` | `make ops-smoke` |
| `/publish` | `POST /ops/publish/run` | `ops_cli.py publish-run` | — |
| `/regenerate` *(new)* | `POST /ops/regenerate` *(new)* | `ops_cli.py regenerate` *(new)* | `make ops-regenerate` *(new)* |

Docs to update:
- `docs/service-setup-run-test.md`: Add regenerate to CLI section, add `OLLAMA_TIMEOUT_SECONDS` to variables section, add troubleshooting for empty translations/drafts
- `.env.example`: Add `OLLAMA_TIMEOUT_SECONDS` with description

## Risks / Trade-offs

**[Risk] Consecutive-failure threshold too high → slow failure detection**
If Ollama crashes, the system will attempt 3 more items before disabling (up to 3 × 300s = 15 minutes). This is acceptable — the `/regenerate` command provides recovery, and 15 minutes is far better than the current 0-second (but permanent) disable.
→ Mitigation: Threshold is configurable via constructor param; can be lowered if needed.

**[Risk] Regeneration of large batches is still slow**
Regenerating 68 empty items sequentially at ~3 minutes each takes ~3.4 hours. This is inherent to the local Ollama model.
→ Mitigation: The Telegram handler sends progress updates. Users can also regenerate specific items with `/regenerate <N>` instead of the entire batch.

**[Risk] `update_payload()` overwrites manually edited drafts**
If a user has already manually edited a `threads_draft` via `/edit`, running `/regenerate` for that item would overwrite it.
→ Mitigation: Only regenerate items where `threads_draft` is empty AND `chinese_translation_full` is empty. Items with any content are skipped unless explicitly targeted by `/regenerate <N>`.

**[Trade-off] Single `OLLAMA_TIMEOUT_SECONDS` for both scoring and review**
Scoring uses simpler prompts and could use a shorter timeout, but a single setting reduces configuration surface. Acceptable trade-off for this project's scale.
