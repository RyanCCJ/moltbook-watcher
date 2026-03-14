## Why

The current ingestion pipeline only scrapes post content without any comment context, missing valuable community signals for quality and relevance scoring. Translation is hardcoded to Traditional Chinese, which doesn't adapt to Moltbook's multilingual environment. After scoring, there is no automated Threads-ready copy generation — operators must manually write promotional text for each approved post. These gaps limit the pipeline's automation level and output quality.

## What Changes

- **Scrape top comments**: When fetching posts, also call Moltbook API `GET /posts/{id}/comments?sort=top` to retrieve the top N popular comments. Include comment text in the Ollama scoring prompt. Store original comments and their translations in ReviewItem as review reference.
- **Configurable translation language**: Add a `TRANSLATION_LANGUAGE` environment variable (e.g., `zh-TW`, `ja`, `ko`). Default to empty string, meaning no translation (translated fields remain empty). Only invoke Ollama translation when a language is explicitly configured. **BREAKING**: The previous default behavior of always translating to Traditional Chinese will change to no translation by default.
- **Configurable Threads language**: Add a separate `THREADS_LANGUAGE` environment variable (default: `en`). This controls the language of auto-generated Threads drafts, independent of `TRANSLATION_LANGUAGE`. For example, an operator can review content translated to Chinese (`TRANSLATION_LANGUAGE=zh-TW`) while publishing Threads drafts in English (`THREADS_LANGUAGE=en`).
- **Auto-generate Threads draft**: When a post's `final_score` meets the publish threshold, use Ollama (start with `think=True`, retry with `think=False` on compatibility errors) to generate a short, natural-sounding Threads post in the configured `THREADS_LANGUAGE`. The draft should avoid bullet points, excessive emoji, and Markdown syntax — instead use a conversational tone that feels human and engaging. The draft must always append the original Moltbook post URL at the end and should be discarded if it is too similar to source content. Store the draft in ReviewItem and use it during publish.
- **DB migration**: Add new columns to ReviewItem for comment snapshots and Threads draft.
- **Documentation sync**: Update README, `.env.example`, and relevant docs to reflect new settings and behaviors.

## Capabilities

### New Capabilities
- `comment-scraping`: Scrape top comments alongside posts, include them in scoring prompts, and store as review reference with translations.
- `threads-draft-gen`: Auto-generate a natural, Threads-optimized short post (using Ollama with `think=True` then fallback to `think=False` on compatibility errors) for articles that pass the score threshold. Draft is written in `THREADS_LANGUAGE` (default: `en`) and always appends the original Moltbook link. Stored in ReviewItem and used at publish time.
- `configurable-translation`: Make translation target language configurable via `TRANSLATION_LANGUAGE` env var (default: no translation). Add separate `THREADS_LANGUAGE` env var (default: `en`) for Threads draft language.

### Modified Capabilities

_(No existing specs in openspec/specs/ — no modifications needed)_

## Impact

- **API Client** (`src/integrations/moltbook_api_client.py`): Add `fetch_comments()` method; extend `MoltbookPost` dataclass with `top_comments` field.
- **Scoring** (`src/services/scoring_service.py`): Scoring prompt must incorporate comment content for richer context.
- **Review Payload** (`src/services/review_payload_service.py`): Translation logic gated by `TRANSLATION_LANGUAGE` setting; add Threads draft generation via Ollama.
- **Models** (`src/models/review_item.py`): Add `top_comments_snapshot`, `top_comments_translated`, and `threads_draft` columns.
- **Workers** (`src/workers/ingestion_worker.py`): Call comments API after fetching posts. `src/workers/review_worker.py`: Pass comment data through. `src/workers/publish_worker.py`: Use `threads_draft` when publishing; if empty, mark publish job terminally failed (no raw-content fallback).
- **Settings** (`src/config/settings.py`): Add `translation_language` and `threads_language` settings.
- **Config files** (`.env.example`, `README.md`, `docs/`): Document new environment variables and changed defaults.
- **DB Migration** (`scripts/migrate.py` or new migration script): Add new ReviewItem columns.
- **Tests**: Update existing tests for affected modules; add new tests for comment scraping, configurable translation, and draft generation.
