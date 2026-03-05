## 1. Settings & Configuration

- [x] 1.1 Add `translation_language: str = ""` field to `Settings` in `src/config/settings.py`
- [x] 1.2 Add `threads_language: str = "en"` field to `Settings` in `src/config/settings.py`
- [x] 1.3 Add `TRANSLATION_LANGUAGE=` and `THREADS_LANGUAGE=en` to `.env.example` with descriptive comments

## 2. Moltbook API Client — Comment Fetching

- [x] 2.1 Create `MoltbookComment` dataclass in `src/integrations/moltbook_api_client.py` with fields: `author_handle: str | None`, `content_text: str`, `upvotes: int`
- [x] 2.2 Add `top_comments: list[MoltbookComment]` field (default `[]`) to `MoltbookPost` dataclass
- [x] 2.3 Implement `async fetch_comments(post_id: str, limit: int = 5, sort: str = "top") -> list[MoltbookComment]` method on `MoltbookAPIClient`
- [x] 2.4 Add error handling in `fetch_comments` — catch exceptions, log warning, return empty list (non-fatal)

## 3. Scoring Service — Include Comments in Prompt

- [x] 3.1 Update `ScoringService.score_candidate()` signature to accept an optional `top_comments` parameter
- [x] 3.2 Update `ScoringService._score_with_ollama()` prompt to include top comment texts and author handles when comments are provided
- [x] 3.3 Update `ScoringService._score_with_heuristic()` to handle the new parameter gracefully (ignore or use comment count)

## 4. Database Migration — ReviewItem New Columns

- [x] 4.1 Add `top_comments_snapshot: Mapped[list]` (JSON, default `[]`) column to `ReviewItem` model
- [x] 4.2 Add `top_comments_translated: Mapped[list]` (JSON, default `[]`) column to `ReviewItem` model
- [x] 4.3 Add `threads_draft: Mapped[str]` (Text, default `""`) column to `ReviewItem` model
- [x] 4.4 Update `ReviewItemRepository.create()` to accept `top_comments_snapshot`, `top_comments_translated`, and `threads_draft` parameters
- [x] 4.5 Create or update migration script to add the new columns to existing databases

## 5. Review Payload Service — Configurable Translation

- [x] 5.1 Update `ReviewPayloadService.__init__()` to accept `translation_language: str` parameter
- [x] 5.2 Refactor `_translate_to_chinese()` into generic `_translate(content: str, target_language: str)` method with dynamic language in the Ollama prompt
- [x] 5.3 Gate translation in `build_payload()`: skip entirely when `translation_language` is empty (translated fields remain empty), call `_translate()` when set
- [x] 5.4 Add comment translation logic: translate `top_comments` list when `translation_language` is set, return empty list otherwise

## 6. Review Payload Service — Threads Draft Generation

- [x] 6.1 Update `ReviewPayloadService.__init__()` to accept `threads_language: str` parameter
- [x] 6.2 Implement `_generate_threads_draft(raw_content: str, top_comments: list, final_score: float, source_url: str) -> str` method
- [x] 6.3 Craft the Ollama prompt: instruct natural conversational tone in `threads_language`, prohibit bullet points / excessive emoji / Markdown, prohibit URLs in output
- [x] 6.4 Use `_chat_with_think_fallback(prompt=..., think=True)` for Ollama call (consistent with scoring pattern)
- [x] 6.5 Programmatically append `\n\n{source_url}` to the Ollama response after `_extract_chat_content()`
- [x] 6.6 Add error handling: on failure, log warning and return empty string (non-fatal)
- [x] 6.7 Update `build_payload()` to accept `final_score` and `source_url`, call `_generate_threads_draft()` when score meets threshold
- [x] 6.8 Update `ReviewPayload` dataclass to include `top_comments_snapshot`, `top_comments_translated`, and `threads_draft` fields
- [x] 6.9 Add guardrail: if generated draft is too similar to source content, discard it and store empty `threads_draft`
- [x] 6.10 Update think compatibility strategy: if `think=True` is rejected, retry with `think=False` (no `thinking` parameter)

## 7. Ingestion Worker — Orchestrate Comment Fetching

- [x] 7.1 Update `IngestionWorker.run_cycle()` to call `fetch_comments()` for each fetched post after dedup check
- [x] 7.2 Attach fetched comments to `MoltbookPost.top_comments` before scoring
- [x] 7.3 Pass `top_comments` to `ScoringService.score_candidate()` call

## 8. Review Worker — Pass Through Comments and Score

- [x] 8.1 Update `ReviewWorker.run_cycle()` to read `CandidatePost` raw content and fetch associated `top_comments` from the stored data (or re-fetch from the `MoltbookPost` dataclass passed through)
- [x] 8.2 Pass `top_comments`, `final_score`, and `source_url` to `ReviewPayloadService.build_payload()`
- [x] 8.3 Pass `top_comments_snapshot`, `top_comments_translated`, and `threads_draft` from `ReviewPayload` to `ReviewItemRepository.create()`

## 9. Publish Worker — Use Threads Draft

- [x] 9.1 Update `PublishWorker._run_single_job()` to query the associated `ReviewItem` for the candidate
- [x] 9.2 Use `ReviewItem.threads_draft` as the text for `threads_client.publish_post()` when non-empty
- [x] 9.3 Mark publish job as terminal failure when `threads_draft` is empty (`missing_threads_draft`), and do not fall back to raw content

## 10. Worker/Service Wiring

- [x] 10.1 Update `runtime.py` (or wherever services are instantiated) to pass `settings.translation_language` to `ReviewPayloadService`
- [x] 10.2 Update `runtime.py` to pass `settings.threads_language` to `ReviewPayloadService`

## 11. Tests

- [x] 11.1 Add unit tests for `MoltbookAPIClient.fetch_comments()` — success, empty, API error scenarios
- [x] 11.2 Add unit tests for `ScoringService` with comments in prompt — with and without comments
- [x] 11.3 Add unit tests for `ReviewPayloadService` translation gating — empty language (skip), set language (translate)
- [x] 11.4 Add unit tests for `ReviewPayloadService._generate_threads_draft()` — success, failure, empty score
- [x] 11.5 Add unit tests for `ReviewPayloadService` source URL appending logic
- [x] 11.6 Update existing `IngestionWorker` tests to account for comment fetching
- [x] 11.7 Update existing `ReviewWorker` tests to account for new payload fields
- [x] 11.8 Update existing `PublishWorker` tests for `threads_draft` usage and no-raw-content fallback behavior

## 12. Documentation

- [x] 12.1 Update `README.md` — document `TRANSLATION_LANGUAGE` and `THREADS_LANGUAGE` settings, note breaking change to translation default
- [x] 12.2 Update `docs/service-setup-run-test.md` if it references translation or environment setup
- [x] 12.3 Update `docs/ollama-and-threads-credentials.md` if it references Threads publishing behavior
- [x] 12.4 Update `docs/data-flow-and-safe-reset.md` if it describes the ingestion/review/publish data flow
