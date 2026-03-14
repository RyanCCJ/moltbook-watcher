# Quickstart: Moltbook Threads Curation Bot

## Purpose

Validate the MVP end-to-end behavior for discovery, scoring, review, scheduling,
and publishing flow on a single-host setup.

## Prerequisites

- Local Mac host runtime environment is available.
- Python runtime and project dependencies are managed with uv.
- Local LLM service is reachable.
- PostgreSQL and Redis services are reachable.
- Moltbook API access is configured per `https://www.moltbook.com/skill.md`.
- One dedicated Threads account is configured for publishing.
- Notification endpoint (SMTP email) is configured for terminal publish failure.

## 1. Start Services

1. Start API service and worker processes via uv-managed commands.
2. Confirm health endpoints for API, worker, queue, and storage are healthy.
3. Confirm publish mode is set to `manual-approval` for initial validation.

## 2. Run Discovery and Scoring Cycle

1. Trigger one ingestion cycle for configured source windows via Moltbook API.
2. Verify candidates are captured and moved to `scored` state.
3. Verify score artifacts exist for novelty, depth, tension, reflective impact,
   engagement, risk, content score, and final score.

Expected result:
- Candidate records are created.
- Final ranking is produced.
- Duplicate content is blocked.

## 3. Review Workflow Validation

1. Open review queue endpoint/UI.
2. Verify each review item includes:
   - English draft
   - Full Chinese translation
   - Risk tags
   - Source URL and capture time
3. Approve a subset and reject at least one item.

Expected result:
- Decisions are persisted.
- Approved items move to publish scheduling pipeline.
- Rejected items do not enter schedule.

## 4. Publishing Validation

1. Run scheduler for current day.
2. Verify planned volume respects 0-5/day constraints.
3. Execute publish worker for approved items.
4. Confirm published records include attribution link.

Expected result:
- Approved items publish to the dedicated Threads account.
- Duplicate publish attempts are blocked.

## 5. Failure Handling Validation

1. Simulate transient publish failure.
2. Verify job retries up to 3 attempts.
3. Simulate terminal failure after retries are exhausted.
4. Verify:
   - Job marked `failed_terminal`
   - Operator notification sent
   - Structured failure logs retained

Expected result:
- Failed item does not block unrelated publish jobs.
- Operator receives failure alert within expected window.

## 6. Archive and Recall Validation

1. Mark queued items as unreviewed long enough for archive policy.
2. Run archive process.
3. Confirm unreviewed items older than 14 days move to `archived`.
4. Generate high-score recall list.

Expected result:
- Archive policy enforced.
- Recall output generated for operator review.

## 7. Test Gate Validation

1. Run unit tests for scoring/routing/dedup/mode-switch/publish gating logic.
2. Run integration tests for full pipeline transitions.
3. Run contract tests for review/publish API contract.

Expected result:
- All required tests pass.
- No business-logic change is merged without unit coverage.

## Runbook Findings (Validated 2026-02-25)

- `uv run --extra dev pytest tests/unit/test_scoring_service.py tests/unit/test_dedup_service.py tests/contract/test_moltbook_source_contract.py tests/integration/test_ingestion_cycle.py`
  - Result: pass
- `uv run --extra dev pytest tests/unit/test_routing_service.py tests/contract/test_review_api_contract.py tests/integration/test_review_workflow.py`
  - Result: pass
- `uv run --extra dev pytest tests/unit/test_publish_mode_service.py tests/unit/test_publish_retry_policy.py tests/contract/test_publish_api_contract.py tests/integration/test_publish_workflow.py`
  - Result: pass
- `uv run --extra dev pytest tests/integration/test_e2e_pipeline.py tests/integration/test_throughput_sla.py tests/unit/test_security_guards.py`
  - Result: pass

Operational notes:
- FastAPI currently uses startup/shutdown event hooks and emits deprecation
  warnings; lifecycle migration to lifespan handlers is a future cleanup item.
- Publish pause mode is global in-process state; tests should inject isolated
  publish control instances when pause behavior is toggled.
