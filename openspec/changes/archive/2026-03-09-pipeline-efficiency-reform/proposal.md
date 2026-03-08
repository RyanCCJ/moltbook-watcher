## Why

The pipeline currently processes every ingested post through the full LLM pipeline (scoring → translation → Threads draft → review item) regardless of quality, pushes every review item to Telegram individually, and has critical features like RoutingService and auto-publish fully implemented but never integrated. Combined with hardcoded ingestion parameters, this creates excessive LLM load (~30-60 min/cycle for 100 posts), Telegram notification overload, and an inability to transition toward semi-automated publishing.

Empirical data from 397 scored posts confirms the scoring model produces a narrow range (1.46–3.65, no post exceeds 4.0), making all threshold-based routing (fast-track ≥ 4.2) and draft generation (≥ 3.5) gates either useless or overly permissive. The system needs configurable thresholds to support iterative calibration alongside the structural fixes.

## What Changes

- **Configurable ingestion parameters**: Add `INGESTION_TIME`, `INGESTION_LIMIT`, `INGESTION_SORT` environment variables with sensible defaults (`hour`, `20`, `top`). Scheduler and runtime read from settings; Telegram `/ingest` and CLI can override.
- **Configurable score thresholds**: Add `REVIEW_MIN_SCORE` (default `3.5`) and `AUTO_PUBLISH_MIN_SCORE` (default `4.0`) environment variables. Both control pipeline behavior and can be tuned without code changes.
- **Low-score filtering in IngestionWorker**: Posts with `final_score < REVIEW_MIN_SCORE` are directly archived (`seen → scored → archived`) — no translation, no Threads draft, no review item created. Full `raw_content` and `top_comments_snapshot` are retained for traceability and semantic dedup; source_url and score_card remain for dedup and analytics. These posts do not enter the recall system (no review_item exists).
- **RoutingService integration**: Wire `RoutingService.route_candidate()` into IngestionWorker after scoring. Store the route decision (`fast_track` / `review_queue` / `risk_priority`) on the score_card or candidate. Remove the redundant `is_follow_up_allowed()` method (FollowUpService already handles this).
- **Semi-auto publish path**: Rename `low-risk-auto` publish mode to `semi-auto` to reflect that the criteria is about both high score and low risk, not risk alone. When `PUBLISH_MODE=semi-auto` and `RoutingService` returns `fast_track`, automatically transition the candidate `queued → approved` (bypassing human review). Add the `QUEUED → APPROVED` lifecycle transition. Require `final_score >= AUTO_PUBLISH_MIN_SCORE` and `risk_score <= 1`. **BREAKING**: `PublishMode.LOW_RISK_AUTO` renamed to `PublishMode.SEMI_AUTO`; env var value changes from `low-risk-auto` to `semi-auto`.
- **Telegram notification reform**: Replace per-item push notifications with a single ingestion digest summary per cycle, including score distribution, risk breakdown, and auto-publish readiness metrics. Operator uses `/pending` to review when ready.
- **Unify default limits**: Align ops API default limit with the new `INGESTION_LIMIT` setting (currently ops API defaults to 20 while everything else defaults to 100).

## Capabilities

### New Capabilities
- `configurable-ingestion`: Environment-variable-driven ingestion parameters (time, limit, sort) with override support from Telegram and CLI
- `score-threshold-gating`: Configurable score thresholds that control which posts enter the review queue and which qualify for auto-publish
- `routing-integration`: RoutingService wired into the ingestion pipeline to classify posts as fast-track, review-queue, or risk-priority
- `auto-publish-pipeline`: End-to-end auto-approve path for high-scoring, low-risk posts when publish mode is `semi-auto`
- `ingestion-digest-notification`: Telegram digest summary replacing per-item push notifications, including auto-publish readiness metrics

### Modified Capabilities
- `telegram-review`: Remove automatic per-item push after ingestion cycle; notifications become opt-in via `/pending`
- `threads-draft-gen`: Draft generation threshold changes from hardcoded `3.5` to configurable `REVIEW_MIN_SCORE` (only posts entering review get drafts)

## Impact

- **Settings** (`src/config/settings.py`): Add 5 new environment variables
- **Models** (`src/models/lifecycle.py`): Add `SCORED → ARCHIVED` transition for low-score filtering; add `QUEUED → APPROVED` transition for auto-approve path; rename `PublishMode.LOW_RISK_AUTO` to `PublishMode.SEMI_AUTO`
- **Models** (`src/models/score_card.py`): Add `route_decision` column to persist routing result
- **Workers** (`src/workers/ingestion_worker.py`): Add score threshold check, RoutingService call, low-score archive, and auto-approve logic
- **Workers** (`src/workers/runtime.py`): Read new settings, replace push_pending_items with digest notification, pass thresholds
- **Workers** (`src/workers/scheduler.py`): Read ingestion time/limit/sort from settings
- **Services** (`src/services/routing_service.py`): Remove `is_follow_up_allowed()`, thresholds configurable via constructor
- **Services** (`src/services/review_payload_service.py`): Accept min_score from settings instead of hardcoded default
- **Telegram** (`src/api/telegram_routes.py`): `/ingest` defaults from settings, override with arguments; new digest message format
- **Telegram** (`src/services/telegram_service.py`): Add `format_ingestion_digest()` method
- **API** (`src/api/ops_routes.py`): Default limit from settings
- **Database**: Migration to add `route_decision` column to `score_cards`
- **Tests**: Update unit tests for new thresholds, routing integration, auto-approve path, and digest notification
