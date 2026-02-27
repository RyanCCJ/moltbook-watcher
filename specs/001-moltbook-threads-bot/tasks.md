---

description: "Task list for implementing Moltbook Threads Curation Bot"
---

# Tasks: Moltbook Threads Curation Bot

**Input**: Design documents from `specs/001-moltbook-threads-bot/`  
**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Tests are REQUIRED by constitution and spec. Write tests first and ensure they fail before implementation.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no dependency on unfinished tasks)
- **[Story]**: User story label (`[US1]`, `[US2]`, `[US3]`)
- Every task includes a concrete file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize project runtime/tooling for uv-managed Python backend.

- [X] T001 Initialize uv-managed Python project and dependency manifest in pyproject.toml
- [X] T002 [P] Create backend source directories and package markers in src/__init__.py
- [X] T003 [P] Create test directory structure and package markers in tests/__init__.py
- [X] T004 Configure lint/test/tool settings in pyproject.toml
- [X] T005 [P] Add environment template for required runtime secrets in .env.example
- [X] T006 [P] Add developer run commands for API, worker, and tests in Makefile

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build core runtime components required by all user stories.

**⚠️ CRITICAL**: No user story implementation starts before this phase completes.

- [X] T007 Implement application settings loader and config validation in src/config/settings.py
- [X] T008 [P] Implement SQLAlchemy base/session and DB lifecycle management in src/models/base.py
- [X] T009 [P] Implement Redis queue client abstraction in src/services/queue_client.py
- [X] T010 Define core enums and lifecycle transition guard in src/models/lifecycle.py
- [X] T011 [P] Implement common structured logging helpers in src/services/logging_service.py
- [X] T012 Implement FastAPI app bootstrap and health endpoints in src/api/app.py
- [X] T013 [P] Implement scheduler bootstrap for hourly ingestion and publish cadence in src/workers/scheduler.py
- [X] T014 [P] Implement notification provider interface and SMTP adapter skeleton in src/integrations/notification_client.py
- [X] T015 Add migration bootstrap for persistence schema in scripts/migrate.py

**Checkpoint**: Foundation complete. User stories can proceed.

---

## Phase 3: User Story 1 - Automated Candidate Discovery and Ranking (Priority: P1) 🎯 MVP

**Goal**: Ingest Moltbook content via API and produce deduplicated ranked candidates.

**Independent Test**: Run one hourly cycle with fixture data and verify candidates are scored/ranked and near-duplicates are filtered.

### Tests for User Story 1 (REQUIRED)

- [X] T016 [P] [US1] Add unit tests for score formula and risk penalty behavior in tests/unit/test_scoring_service.py
- [X] T017 [P] [US1] Add unit tests for semantic dedup filtering behavior in tests/unit/test_dedup_service.py
- [X] T018 [P] [US1] Add contract tests for Moltbook source API adapter against source contract in tests/contract/test_moltbook_source_contract.py
- [X] T019 [P] [US1] Add integration test for ingestion-to-scored lifecycle flow in tests/integration/test_ingestion_cycle.py

### Implementation for User Story 1

- [X] T020 [P] [US1] Implement CandidatePost persistence model and repository in src/models/candidate_post.py
- [X] T021 [P] [US1] Implement ScoreCard persistence model and repository in src/models/score_card.py
- [X] T022 [P] [US1] Implement Moltbook API client (no scraping) in src/integrations/moltbook_api_client.py
- [X] T023 [US1] Implement local LLM scoring service for candidate scoring dimensions in src/services/scoring_service.py
- [X] T024 [US1] Implement dedup fingerprint and similarity decision service in src/services/dedup_service.py
- [X] T025 [US1] Implement ingestion worker to fetch, score, dedup, and persist candidates in src/workers/ingestion_worker.py
- [X] T026 [US1] Add ingestion cycle metrics/log events for throughput and latency in src/workers/ingestion_worker.py

**Checkpoint**: Candidate discovery/ranking works and is independently testable.

---

## Phase 4: User Story 2 - Reviewer-Centered Filtering Workflow (Priority: P2)

**Goal**: Provide a complete review queue with translation, risk context, and operator decision handling.

**Independent Test**: Open review APIs with seeded candidates; verify queue output fields and decision transitions.

### Tests for User Story 2 (REQUIRED)

- [X] T027 [P] [US2] Add unit tests for queue routing thresholds and follow-up gating in tests/unit/test_routing_service.py
- [X] T028 [P] [US2] Add contract tests for review item and decision endpoints in tests/contract/test_review_api_contract.py
- [X] T029 [P] [US2] Add integration test for review decision lifecycle transitions in tests/integration/test_review_workflow.py

### Implementation for User Story 2

- [X] T030 [P] [US2] Implement ReviewItem persistence model and repository in src/models/review_item.py
- [X] T031 [P] [US2] Implement FollowUpCandidate persistence model and repository in src/models/follow_up_candidate.py
- [X] T032 [US2] Implement routing service for fast-track, review queue, and risk priority queues in src/services/routing_service.py
- [X] T033 [US2] Implement translation payload builder for review items in src/services/review_payload_service.py
- [X] T034 [US2] Implement review list and decision API endpoints in src/api/review_routes.py
- [X] T035 [US2] Implement 14-day archive worker and high-score recall generation in src/workers/archive_worker.py
- [X] T036 [US2] Add review action audit logging and mode-change event logging in src/services/audit_service.py

**Checkpoint**: Review workflow is fully functional and independently testable.

---

## Phase 5: User Story 3 - Scheduled Auto-Publishing to Threads (Priority: P3)

**Goal**: Schedule approved items and publish to one Threads account with retries, notifications, and pause controls.

**Independent Test**: Approve items, run publish worker, verify publish outcomes, retry behavior, terminal notifications, and duplicate blocking.

### Tests for User Story 3 (REQUIRED)

- [X] T037 [P] [US3] Add unit tests for publish mode switching and gating rules in tests/unit/test_publish_mode_service.py
- [X] T038 [P] [US3] Add unit tests for retry policy and terminal failure transitions in tests/unit/test_publish_retry_policy.py
- [X] T039 [P] [US3] Add contract tests for publish mode/pause/job endpoints in tests/contract/test_publish_api_contract.py
- [X] T040 [P] [US3] Add integration test for scheduled publish with retries and notification in tests/integration/test_publish_workflow.py

### Implementation for User Story 3

- [X] T041 [P] [US3] Implement PublishJob persistence model and repository in src/models/publish_job.py
- [X] T042 [P] [US3] Implement PublishedPostRecord persistence model and duplicate guard repository in src/models/published_post_record.py
- [X] T043 [P] [US3] Implement NotificationEvent persistence model in src/models/notification_event.py
- [X] T044 [US3] Implement Threads publish adapter client in src/integrations/threads_client.py
- [X] T045 [US3] Implement publish scheduler and execution worker with non-blocking retries in src/workers/publish_worker.py
- [X] T046 [US3] Implement terminal failure notification dispatch with SMTP provider in src/services/notification_service.py
- [X] T047 [US3] Implement publish mode and pause-control API endpoints in src/api/publish_routes.py
- [X] T048 [US3] Implement follow-up eligibility evaluator (novelty delta + cooldown) in src/services/follow_up_service.py

**Checkpoint**: Auto-publish workflow is fully functional and independently testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final quality hardening across user stories.

- [X] T049 [P] Add end-to-end smoke test for full candidate-to-publish lifecycle in tests/integration/test_e2e_pipeline.py
- [X] T050 [P] Add performance validation for >=500 candidates/day and hourly cycle SLA in tests/integration/test_throughput_sla.py
- [X] T051 [P] Add security checks for secret handling and credential redaction in logs in tests/unit/test_security_guards.py
- [X] T052 [P] Update operator and developer documentation in docs/plans/2026-02-24-moltbook-curation-design.md
- [X] T053 Validate quickstart scenarios and update runbook findings in specs/001-moltbook-threads-bot/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies; start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1; blocks all user stories.
- **Phase 3 (US1)**: Depends on Phase 2; defines MVP baseline.
- **Phase 4 (US2)**: Depends on Phase 2 and uses seeded/produced candidates from US1 interfaces.
- **Phase 5 (US3)**: Depends on Phase 2 and approved review outputs from US2.
- **Phase 6 (Polish)**: Depends on all selected user story phases.

### User Story Completion Order

1. **US1 (P1)**: Deliver ingestion, scoring, and dedup baseline.
2. **US2 (P2)**: Deliver operator review workflow and archival controls.
3. **US3 (P3)**: Deliver scheduled publish automation and reliability controls.

### Within Each User Story

- Tests first (unit -> contract -> integration) and confirm failing baseline.
- Models/repositories before services.
- Services before API/worker orchestration.
- Story phase must be independently verifiable before moving on.

---

## Parallel Execution Examples

### User Story 1

```bash
# Parallel test authoring
T016, T017, T018, T019

# Parallel model/integration adapter work
T020, T021, T022
```

### User Story 2

```bash
# Parallel tests
T027, T028, T029

# Parallel model work
T030, T031
```

### User Story 3

```bash
# Parallel tests
T037, T038, T039, T040

# Parallel persistence models
T041, T042, T043
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup).
2. Complete Phase 2 (Foundational).
3. Complete Phase 3 (US1).
4. Validate US1 independently with test and quickstart checks.
5. Demo candidate ranking quality before expanding scope.

### Incremental Delivery

1. Ship US1 baseline for discovery and ranking.
2. Add US2 for human-governed review workflows.
3. Add US3 for automated publish execution with safeguards.
4. Run Phase 6 hardening and operational validation.

### Suggested MVP Scope

- Recommended MVP scope for first implementation pass: **Phase 1 + Phase 2 + Phase 3 (US1)**.

---

## Notes

- [P] tasks are safe for parallel work only when dependencies are already complete.
- Every story task includes file paths and story labels.
- Unit-test coverage for changed business logic is mandatory by constitution.
- Moltbook ingestion in MVP is API-based and does not use scraping.
