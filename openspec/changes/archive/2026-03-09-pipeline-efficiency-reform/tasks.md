## 1. Settings & Configuration

- [x] 1.1 Add `INGESTION_TIME`, `INGESTION_LIMIT`, `INGESTION_SORT` fields to `Settings` in `src/config/settings.py` with defaults (`hour`, `20`, `top`) and validation (Literal types, ge/le constraints)
- [x] 1.2 Add `REVIEW_MIN_SCORE` (float, default `3.5`) and `AUTO_PUBLISH_MIN_SCORE` (float, default `4.0`) fields to `Settings`
- [x] 1.3 Rename `publish_mode` Literal type from `"manual-approval" | "low-risk-auto"` to `"manual-approval" | "semi-auto"` in `Settings`
- [x] 1.4 Add `INGESTION_TIME`, `INGESTION_LIMIT`, `INGESTION_SORT`, `REVIEW_MIN_SCORE`, `AUTO_PUBLISH_MIN_SCORE` entries to `.env.example`
- [x] 1.5 Update `.env` to use `PUBLISH_MODE=manual-approval` (verify no `low-risk-auto` references remain)

## 2. Lifecycle & Models

- [x] 2.1 Add `SCORED → ARCHIVED` to `_ALLOWED_CANDIDATE_TRANSITIONS` in `src/models/lifecycle.py`
- [x] 2.2 Add `QUEUED → APPROVED` to `_ALLOWED_CANDIDATE_TRANSITIONS` in `src/models/lifecycle.py`
- [x] 2.3 Rename `PublishMode.LOW_RISK_AUTO` to `PublishMode.SEMI_AUTO` (value `"semi-auto"`) in `src/models/lifecycle.py`
- [x] 2.4 Add `route_decision` column (VARCHAR(32), nullable, default NULL) to `ScoreCard` model in `src/models/score_card.py`
- [x] 2.5 Create Alembic migration for `route_decision` column on `score_cards` table
- [x] 2.6 Update `ScoreCardRepository.create()` to accept optional `route_decision` parameter

## 3. RoutingService Cleanup & Integration

- [x] 3.1 Remove `is_follow_up_allowed()` method from `src/services/routing_service.py`
- [x] 3.2 Make `RoutingService` thresholds configurable via constructor (`fast_track_min_score`, `fast_track_max_risk`) with defaults from `AUTO_PUBLISH_MIN_SCORE`
- [x] 3.3 Wire `RoutingService.route_candidate()` call into `IngestionWorker.run_cycle()` after scoring, before lifecycle transitions
- [x] 3.4 Pass `route_decision` result to `ScoreCardRepository.create()` to persist routing classification

## 4. Score Threshold Gating (IngestionWorker)

- [x] 4.1 Add `review_min_score` parameter to `IngestionWorker` constructor (read from Settings)
- [x] 4.2 After scoring + routing, check `final_score < review_min_score`: if true, transition candidate `scored → archived` (retain full raw_content, score_card, comments)
- [x] 4.3 After scoring + routing, check `final_score >= review_min_score`: if true, transition candidate `scored → queued` (existing behavior)
- [x] 4.4 Track archived count in cycle metrics and return it alongside `persisted_count` and `scored_count`

## 5. Semi-Auto Publish Path

- [x] 5.1 Update `PublishControlService` in `src/services/publish_mode_service.py`: rename `LOW_RISK_AUTO` references to `SEMI_AUTO`
- [x] 5.2 Add semi-auto logic in `IngestionWorker`: when `publish_mode == "semi-auto"` and `route_decision == "fast_track"`, transition candidate `queued → approved`
- [x] 5.3 Ensure `ReviewWorker` creates review_item for auto-approved candidates with `decision="approved"` and `reviewed_by="semi-auto"`
- [x] 5.4 Verify `PublishWorker` picks up auto-approved candidates normally (no changes expected, but confirm)

## 6. Entry Point Parameter Unification

- [x] 6.1 Update `runtime.run_ingestion_once()` signature: replace hardcoded defaults with Settings values (`settings.ingestion_time`, `settings.ingestion_limit`, `settings.ingestion_sort`)
- [x] 6.2 Update `scheduler.py`: pass Settings-based defaults to ingestion cycle calls
- [x] 6.3 Update `ops_routes.py`: use `settings.ingestion_limit`, `settings.ingestion_time`, `settings.ingestion_sort` as Query defaults
- [x] 6.4 Update `telegram_routes.py`: replace `_DEFAULT_INGEST_*` constants with Settings values; keep user argument override logic

## 7. Telegram Digest Notification

- [x] 7.1 Add `format_ingestion_digest()` method to `TelegramService` accepting cycle metrics (fetched, persisted, archived, score breakdown, risk breakdown, auto-publish count, pending total)
- [x] 7.2 Implement digest format with ⭐/✅/📦 score bands, risk summary, auto-publish readiness, pending count, and `/pending to review` hint
- [x] 7.3 Replace `push_pending_items()` call in `runtime.run_ingestion_once()` with digest notification (send only when `persisted_count > 0`)
- [x] 7.4 Update `run_ingestion_once()` to collect and pass the required metrics to the digest formatter

## 8. ReviewPayloadService Threshold Update

- [x] 8.1 Update `ReviewPayloadService.__init__()`: accept `threads_draft_min_score` from Settings (`REVIEW_MIN_SCORE`) instead of hardcoded `3.5`
- [x] 8.2 Update all `ReviewPayloadService` instantiation sites to pass the configured threshold

## 9. Tests

- [x] 9.1 Update `tests/unit/test_routing_service.py`: remove tests for `is_follow_up_allowed()`, add tests for configurable thresholds
- [x] 9.2 Add unit tests for new lifecycle transitions (`SCORED → ARCHIVED`, `QUEUED → APPROVED`)
- [x] 9.3 Add unit tests for `IngestionWorker` score threshold gating (low-score archive, high-score queue)
- [x] 9.4 Add unit tests for semi-auto approve path in `IngestionWorker`
- [x] 9.5 Add unit tests for `format_ingestion_digest()` in `TelegramService`
- [x] 9.6 Update `tests/unit/test_publish_mode_service.py`: rename `LOW_RISK_AUTO` to `SEMI_AUTO` references
- [x] 9.7 Add integration test: full ingestion cycle with mixed scores verifying correct routing (archive vs queue vs auto-approve)

## 10. Documentation & Cleanup

- [x] 10.1 Update `README.md`: document new environment variables and their defaults
- [x] 10.2 Update `docs/data-flow-and-safe-reset.md`: reflect new lifecycle paths (scored → archived, queued → approved)
- [x] 10.3 Search codebase for remaining `low-risk-auto` or `LOW_RISK_AUTO` references and replace with `semi-auto` / `SEMI_AUTO`
