## Context

The moltbook-watcher pipeline processes posts through two sequential workers within a single database transaction:

1. **IngestionWorker** — fetches posts from the Moltbook API, fetches comments for each, scores each post via Ollama (synchronous `httpx.Client`, 60s timeout).
2. **ReviewWorker** — for each queued candidate, re-fetches comments from the Moltbook API, translates content + up to 5 comments individually (6 separate Ollama calls, 180s timeout each), and optionally generates a Threads draft (1 additional Ollama call).

Both workers run inside `run_ingestion_once()` sharing one `AsyncSession` and one transaction. The Ollama HTTP calls use synchronous `httpx.Client`, blocking the async event loop.

**Current per-post cost**: up to 9 Ollama calls (1–2 scoring + 6 translation + 1 Threads draft), all serial. With `limit=10`, total wall time can reach 15+ minutes within a single transaction.

## Goals / Non-Goals

**Goals:**

- Reduce Ollama call count per post from ~9 to ~4 by batching translations into a single JSON-structured LLM call.
- Eliminate redundant Moltbook API calls by caching comments fetched during ingestion.
- Prevent event-loop blocking by wrapping synchronous Ollama calls with `asyncio.to_thread()`.
- Improve transaction hygiene by splitting ingestion and review into separate commits.
- Maintain full backward compatibility — no changes to public API contracts or user-facing configuration.

**Non-Goals:**

- Migrating Ollama clients to fully native `httpx.AsyncClient` (too invasive; `asyncio.to_thread()` is sufficient for now).
- Adding parallel Ollama inference via `asyncio.gather()` (depends on hardware; can be layered on later).
- Introducing an external message broker (Celery, RabbitMQ) — current scale does not warrant it.
- Changing the scoring prompt or Threads draft generation logic.

## Decisions

### Decision 1: Batch translation via JSON-structured prompt

**Choice**: Combine content + up to 5 comment translations into a single Ollama call using a JSON input/output contract with `response_format` schema enforcement.

**Alternatives considered**:
- *XML-tag delimited sections*: LLMs handle XML well, but parsing is fragile (tags can be mangled) and Ollama's `format` parameter cannot enforce XML structure.
- *Numbered block separators*: Simplest prompt but most fragile — multi-line translations make boundary detection unreliable.

**Rationale**: JSON input/output is the most robust because (a) Ollama supports `format` for JSON schema constraints, (b) parsing is trivial (`json.loads`), (c) the codebase already uses this pattern in `ScoringService._score_with_ollama`.

**Fallback**: If batch JSON parsing fails, fall back to sequential per-item `_translate()` calls (existing behavior), ensuring no data loss.

### Decision 2: `asyncio.to_thread()` over full async client migration

**Choice**: Wrap existing synchronous `httpx.Client.post()` calls in `asyncio.to_thread()` within both `ScoringService` and `ReviewPayloadService`.

**Alternatives considered**:
- *Full `httpx.AsyncClient` migration*: Would require rewriting `_chat_with_think_fallback`, `_score_with_ollama`, and all test mocks. High churn for marginal benefit given that Ollama processes one request at a time anyway.
- *No change*: Leaves the event loop blocked during LLM inference, making FastAPI `/health` and other endpoints unresponsive during ingestion cycles.

**Rationale**: `asyncio.to_thread()` is a one-line wrapper that unblocks the event loop without restructuring the client lifecycle or tests.

### Decision 3: Persist comments in candidate_posts table

**Choice**: Add a `top_comments_snapshot` JSON column to the `candidate_posts` table. The ingestion worker writes fetched comments; the review worker reads them directly.

**Alternatives considered**:
- *Separate `comments` table*: More normalized, but adds join complexity and a migration for a read-once-write-once pattern. Not worth it for up to 5 short comments per post.
- *In-memory handoff*: Would require both workers to run in the same call frame. Already the case today, but breaks if we later split them into separate processes.

**Rationale**: A JSON column is simple, schema-compatible with the existing `top_comments_snapshot` field on `ReviewItem`, and avoids extra joins. SQLAlchemy's `JSON` type handles serialization automatically.

### Decision 4: Split ingestion and review transactions

**Choice**: In `run_ingestion_once()`, commit after ingestion completes, then run the review cycle in a new session/transaction.

**Alternatives considered**:
- *Keep single transaction*: Simpler, but a 15-minute transaction stresses the database connection pool and risks lock timeouts.
- *Per-post commits*: Too granular; increases commit overhead and complicates metrics aggregation.

**Rationale**: Two-phase commit (ingest → commit → review → commit) balances atomicity and duration. If review fails, ingested candidates remain in the database for the next review cycle.

## Risks / Trade-offs

- **Batch translation quality** — LLM may produce lower-quality translations when handling multiple items in one prompt. → Mitigation: fallback to sequential translation; can A/B test quality.
- **JSON column growth** — Storing comments as JSON in `candidate_posts` denormalizes the schema. → Mitigation: comments are small (5 items × ~200 chars); acceptable trade-off.
- **`asyncio.to_thread()` thread pool** — Default thread pool size is 40. Heavy concurrent usage could exhaust it. → Mitigation: Ollama is single-threaded anyway; at most 1–2 threads used during a cycle.
- **Transaction split data consistency** — If review fails after ingestion commit, candidates exist without review items. → Mitigation: The review worker already handles this case — it picks up un-reviewed candidates on the next cycle.

## Open Questions

- Should we add an `OLLAMA_TIMEOUT_SECONDS` environment variable to make Ollama timeouts configurable, rather than hardcoded at 60s/180s?
- Should the batch translation prompt use `think=True` or `think=False`? Translation is a faithful task (favoring `think=False`), but some models produce better structured output with thinking enabled.
