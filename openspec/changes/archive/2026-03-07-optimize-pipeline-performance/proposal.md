## Why

The ingestion-to-review pipeline suffers from severe performance bottlenecks that cause timeout errors during testing and will block production scalability. The root cause is **serial, synchronous Ollama LLM calls** — each post triggers up to 8–9 individual inference requests (scoring, translation of content + 5 comments, Threads draft generation), all executed sequentially within a single database transaction. Additionally, comments fetched during ingestion are re-fetched during review, wasting API quota and adding unnecessary latency. With even modest `limit` values (≥5), the total wall-clock time easily exceeds the CLI's 180-second HTTP timeout.

## What Changes

- **Batch translation**: Consolidate 6 individual Ollama translation calls (1 content + up to 5 comments) into a single JSON-structured LLM call per post, reducing translation time by ~66%.
- **Non-blocking Ollama calls**: Wrap synchronous `httpx.Client` Ollama calls with `asyncio.to_thread()` (or migrate to `httpx.AsyncClient`) so that long-running LLM inference does not block the async event loop, keeping FastAPI health checks and other endpoints responsive.
- **Comment caching**: Persist top comments fetched during ingestion to the database so the review worker reads cached data instead of making redundant Moltbook API calls.
- **Transaction splitting**: Separate the ingestion and review phases into independent database transactions so that a slow review cycle does not hold open a long-lived transaction or cause cascading rollbacks.

## Capabilities

### New Capabilities

- `batch-translation`: Defines the batched JSON translation prompt contract, response schema, and fallback-to-sequential behavior when the batch call fails.
- `comment-caching`: Defines how ingestion-phase comments are persisted and how the review worker retrieves them without re-fetching from the Moltbook API.

### Modified Capabilities

- `configurable-translation`: The translation mechanism changes from per-item sequential calls to a batch call. The user-facing configuration (language selection via env var) stays the same, but the internal translation interface changes.

## Impact

- **Code**: `ReviewPayloadService` (new `_translate_batch` method, modified `build_payload`), `ScoringService` (async wrapper or client swap), `IngestionWorker` (persist comments), `ReviewWorker` (read cached comments, split transaction), `runtime.py` (transaction boundary changes).
- **Database**: New column or related table for storing top comments on `candidate_posts`.
- **Dependencies**: No new external dependencies; `httpx` and `asyncio` are already available.
- **API**: No public API contract changes; internal service interfaces change.
- **Risk**: Low — all changes are internal implementation improvements with fallback paths.
