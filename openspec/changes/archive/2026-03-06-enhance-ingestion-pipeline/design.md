## Context

Moltbook Watcher is a FastAPI + worker pipeline that ingests posts from Moltbook, scores them with Ollama, builds a review queue, and publishes approved content to Threads. The current pipeline flow is:

1. **Ingestion** (`ingestion_worker.py`): Fetches posts via `MoltbookAPIClient.list_posts()`, deduplicates, scores with `ScoringService`, persists `CandidatePost` + `ScoreCard`.
2. **Review** (`review_worker.py`): For queued candidates, `ReviewPayloadService` generates an English draft and hardcoded Traditional Chinese translation, creating a `ReviewItem`.
3. **Publish** (`publish_worker.py`): Approved candidates are published to Threads using `raw_content` directly.

Key constraints:
- Ollama is the sole LLM backend (no external API dependencies).
- All Ollama calls use `_chat_with_think_fallback` to handle param compatibility.
- The Moltbook API follows the patterns documented in the moltbook skill (`GET /posts/{id}/comments?sort=top` for comments).
- SQLite is the default local DB; PostgreSQL in production.

## Goals / Non-Goals

**Goals:**
- Enrich scoring context by including top comments from each post.
- Make translation language configurable via `TRANSLATION_LANGUAGE` env var; default to no translation.
- Make Threads draft language independently configurable via `THREADS_LANGUAGE` env var; default to `en`.
- Auto-generate a Threads-optimized draft (with original Moltbook link appended) for posts that pass the score threshold.
- Store comment snapshots (original + translated) and Threads drafts in ReviewItem for operator review.
- Maintain backward compatibility for existing data (additive-only schema changes).

**Non-Goals:**
- Changing the scoring algorithm weights or dimensions (novelty, depth, etc.).
- Supporting real-time comment streaming or webhooks.
- Multi-language draft generation per post (Threads draft uses a single configured `THREADS_LANGUAGE`, not per-post language detection).
- Paginated comment fetching — top N from first page is sufficient.

## Decisions

### 1. Comment fetching integrated into MoltbookAPIClient

**Choice**: Add a `fetch_comments(post_id, limit, sort)` async method to `MoltbookAPIClient` that returns a list of comment dataclasses.

**Why**: Follows the existing client pattern. The Moltbook API supports `GET /posts/{POST_ID}/comments?sort=top` with structured JSON responses. Keeping it in the same client avoids a new integration layer.

**Alternative considered**: A separate `MoltbookCommentClient` — rejected because comments are tightly coupled to posts and the existing client already handles auth/pagination patterns.

### 2. Comments stored as JSON snapshot in ReviewItem

**Choice**: Store comments as a JSON list in `top_comments_snapshot` (original) and `top_comments_translated` (translated) columns on `ReviewItem`, rather than a separate `Comment` table.

**Why**: Comments are reference-only context for the operator reviewing the post. They don't need indexing, querying, or independent lifecycle management. A JSON column keeps the schema simple and the data self-contained within each review item.

**Alternative considered**: A normalized `review_comments` table with foreign keys — rejected because it adds migration complexity and query joins without clear benefit for a read-only snapshot.

### 3. Translation gated by TRANSLATION_LANGUAGE env var

**Choice**: Add `translation_language: str = ""` to `Settings`. When empty, `ReviewPayloadService` skips translation entirely and keeps translated fields empty. When set (e.g., `zh-TW`), it translates to that language.

**Why**: Moltbook content spans multiple languages. Forcing translation to a single language wastes Ollama cycles when the operator reads the original language. An empty default reduces compute and makes translation explicitly opt-in.

**Breaking change mitigation**: Document clearly in `.env.example` and README. Users who relied on automatic Chinese translation just need to add `TRANSLATION_LANGUAGE=zh-TW` to their `.env`.

### 4. Separate THREADS_LANGUAGE for draft generation

**Choice**: Add `threads_language: str = "en"` to `Settings`, independent from `translation_language`. The Threads draft is always generated in `threads_language`, regardless of what `translation_language` is set to.

**Why**: Translation serves the operator reviewing content (e.g., a Chinese-speaking operator sets `TRANSLATION_LANGUAGE=zh-TW`). The Threads draft serves the audience reading the published post (e.g., an English-speaking Threads audience gets `THREADS_LANGUAGE=en`). These are fundamentally different audiences with potentially different language needs. Coupling them would force operators to choose between their own review language and their audience's language.

**Default to `en`**: English is the most common language on Threads and the safest default. Unlike `translation_language` (which defaults to empty/no-op), `threads_language` should always have a value so draft generation always produces a usable result.

### 5. Threads draft generation in ReviewPayloadService

**Choice**: Add a `_generate_threads_draft()` method to `ReviewPayloadService` that takes the raw content, comments, score, and `source_url` to produce a short, natural-sounding Threads post. The draft is generated only when `final_score` meets the threshold. The Ollama call starts with `think=True`; if rejected for compatibility reasons, it retries with `think=False` (without using a `thinking` parameter). Drafts that are too similar to source content are discarded.

**Why**: `ReviewPayloadService` already handles all Ollama-based content transformation (translation). Adding draft generation here keeps the Ollama interaction pattern consistent (same client, same `_chat_with_think_fallback` logic, same error handling). The compatibility retry avoids model-specific failures (e.g., models that reject thinking mode) while preserving output quality.

**Prompt design**: The system prompt will instruct the model to:
- Write in a conversational, human tone — no bullet points, no excessive emoji, no Markdown.
- Highlight why the content is interesting, thought-provoking, or informative, tailored to the post's nature.
- Write in the language specified by `THREADS_LANGUAGE` (default: `en`).
- The generated text must NOT include the source URL — the URL is appended programmatically after generation to ensure correctness.

**Source URL handling**: After Ollama returns the draft text, the service appends `\n\n{source_url}` to the draft. This ensures every published Threads post links back to the original Moltbook content, and the URL is never hallucinated or malformed by the model.

**Alternative considered**: A separate `ThreadsDraftService` — rejected because it would duplicate the Ollama client setup and the `_chat_with_think_fallback` pattern already in `ReviewPayloadService`.

### 6. Ingestion worker orchestrates comment fetching

**Choice**: After fetching posts in `IngestionWorker.run_cycle()`, iterate each post and call `fetch_comments()` before scoring. Attach comments to the `MoltbookPost` dataclass so both scoring and review can use them.

**Why**: Comments must be available at scoring time (to enrich the prompt) and at review-item creation time (to snapshot). Fetching them early in ingestion ensures a single-pass flow.

**Rate limiting**: Add a small configurable limit (default 5 comments per post) to avoid hammering the API for posts with hundreds of comments.

### 7. Publish worker uses threads_draft

**Choice**: When `PublishWorker._run_single_job()` publishes to Threads, it reads the associated `ReviewItem.threads_draft` via a join. If `threads_draft` is non-empty, use it; otherwise mark the publish job as terminally failed (`missing_threads_draft`) and do not publish raw content.

**Why**: Prevents accidental publication of unreviewed/unsuitable raw text and keeps publish behavior aligned with explicit review output.

## Risks / Trade-offs

**[Increased Ollama latency]** → Each ingestion cycle now makes 1 extra API call per post (comments) and 1 extra Ollama call per qualifying post (draft generation). Mitigation: Comment fetching is a lightweight HTTP call; draft generation only triggers for posts above the score threshold, which is a small subset. Ollama timeout is already 180s for review payload.

**[Breaking translation default]** → Users who relied on automatic Chinese translation will get untranslated content after upgrade. Mitigation: Clear documentation in README and `.env.example`; migration notes in release.

**[Comment API availability]** → If the Moltbook comments endpoint is down or returns empty, scoring should still work with post-only context. Mitigation: Treat comment fetching errors as non-fatal — log a warning and proceed with empty comments.

**[Draft quality variance]** → Small local models (e.g., qwen3:4b) may produce inconsistent draft quality. Mitigation: The draft is stored for operator review before publishing; operators can edit or reject.

**[JSON column portability]** → SQLite and PostgreSQL both support JSON columns, but query syntax differs. Mitigation: These columns are write-once/read-only snapshots — no complex JSON queries needed.
