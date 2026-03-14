## 1. Comment Caching (Database + Ingestion)

- [x] 1.1 Add `top_comments_snapshot` JSON column to `candidate_posts` model (`src/models/candidate_post.py`) with default `[]`
- [x] 1.2 Create database migration to add `top_comments_snapshot` column (backfill existing rows with `[]`)
- [x] 1.3 Update `CandidatePostRepository.create()` to accept and persist `top_comments_snapshot`
- [x] 1.4 Update `IngestionWorker.run_cycle()` to serialize fetched comments and pass them to `create()`
- [x] 1.5 Add unit tests for comment persistence (post with comments, post without comments, post without `source_post_id`)

## 2. Comment Caching (Review Worker)

- [x] 2.1 Update `ReviewWorker.run_cycle()` to read `top_comments_snapshot` from the candidate record instead of calling `MoltbookAPIClient.fetch_comments()`
- [x] 2.2 Add deserialization logic to convert JSON snapshot back to `MoltbookComment` objects
- [x] 2.3 Remove `moltbook_client` dependency from `ReviewWorker.__init__()` (no longer needed for comment fetching)
- [x] 2.4 Update `runtime.py` to stop passing `moltbook_client` to `ReviewWorker`
- [x] 2.5 Add unit tests verifying the review worker reads cached comments and makes no Moltbook API calls

## 3. Batch Translation

- [x] 3.1 Add `_translate_batch()` method to `ReviewPayloadService` — construct JSON input, build dynamic `response_format` schema, call Ollama, parse JSON output
- [x] 3.2 Add fallback logic in `_translate_batch()` — on failure, call sequential `_translate()` + `_translate_comments()`
- [x] 3.3 Update `build_payload()` to call `_translate_batch()` instead of separate `_translate()` and `_translate_comments()` when `_translation_language` is set
- [x] 3.4 Add unit tests for `_translate_batch()` — happy path, empty comments, empty content, JSON parse failure fallback, HTTP error fallback
- [x] 3.5 Add integration-style test verifying batch translation output matches expected structure (translated_content string + translated_comments list with metadata)

## 4. Non-blocking Ollama Calls

- [x] 4.1 Wrap `ScoringService._chat_with_think_fallback()` internal `self._ollama_client.post()` calls with `asyncio.to_thread()`
- [x] 4.2 Change `ScoringService._score_with_ollama()` to `async` and update `score_candidate()` to `async`
- [x] 4.3 Update `IngestionWorker.run_cycle()` to `await` the now-async `score_candidate()`
- [x] 4.4 Wrap `ReviewPayloadService._chat_with_think_fallback()` internal `self._ollama_client.post()` calls with `asyncio.to_thread()`
- [x] 4.5 Change `_translate`, `_translate_batch`, `_generate_threads_draft`, and `build_payload` to `async`
- [x] 4.6 Update `ReviewWorker.run_cycle()` to `await` the now-async `build_payload()`
- [x] 4.7 Update all affected tests to use `async` test functions and `await` async methods

## 5. Transaction Splitting

- [x] 5.1 Refactor `run_ingestion_once()` in `runtime.py` to commit after `ingestion_worker.run_cycle()` completes, then open a new session for `review_worker.run_cycle()`
- [x] 5.2 Ensure review worker failure does not roll back ingestion results
- [x] 5.3 Add test verifying that ingestion data persists even if review worker raises an exception
- [x] 5.4 Update `scheduler.py` error logging to distinguish ingestion vs. review failures

## 6. Verification and Cleanup

- [x] 6.1 Run full test suite and verify all existing tests pass
- [x] 6.2 Run `ops_cli.py smoke --limit 5` end-to-end test to validate performance improvement
- [x] 6.3 Verify FastAPI `/health` endpoint remains responsive during an active ingestion cycle
- [x] 6.4 Update `README.md` or docs if any operational behavior changed (e.g., transaction semantics)
