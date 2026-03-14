# Implementation Plan: Moltbook Threads Curation Bot

**Branch**: `001-moltbook-threads-bot` | **Date**: 2026-02-24 | **Spec**: `specs/001-moltbook-threads-bot/spec.md`
**Input**: Feature specification from `specs/001-moltbook-threads-bot/spec.md`

## Summary

Build a single-host MVP service that discovers public Moltbook discussions,
ranks candidate content with a local LLM, routes items into review and publish
queues, and auto-publishes approved items to one dedicated Threads account.
Moltbook ingestion is API-based (per skill instructions), not crawler-based.
Design priority is stable operation, strict duplicate prevention, unit-tested
business logic, and low daily operator workload.

## Technical Context

**Language/Version**: Python 3.12 (managed with uv)  
**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy, Redis client, PostgreSQL driver, Ollama client, HTTP client for Moltbook API, APScheduler  
**Storage**: PostgreSQL (system of record), Redis (queue/cache), local file logs for operational diagnostics  
**Testing**: pytest, pytest-asyncio, contract validation tests  
**Target Platform**: macOS on local Mac Studio M4 Max (single-host runtime)  
**Project Type**: Single-project backend service with review API and scheduler workers  
**Performance Goals**: Process >=500 candidates/day; complete each hourly cycle within 60 minutes; send terminal publish failure notification within 5 minutes  
**Constraints**: No k8s deployment for MVP runtime; one Threads account; 0-5 posts/day; 14-day archive window; retry publish 3 times before terminal failure; use Moltbook API ingestion (no scraping in MVP)  
**Scale/Scope**: Single operator, review recommendation cap 10/day, hourly ingestion/scoring cycles, one dedicated content source domain

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] `I. Spec-Driven Delivery`: `spec.md` and this `plan.md` are aligned to the same branch scope; generated artifacts are explicitly linked.
- [x] `II. Independently Valuable Increments`: Plan preserves independent delivery slices (discovery/scoring, review workflow, publish automation).
- [x] `III. Test-First Verification and Unit Coverage`: Unit-test requirements for scoring/routing/dedup/publish gating are explicit and required for changed business logic.
- [x] `IV. Operability and Traceability`: Logging, metrics, alerting, retries, and lifecycle-state persistence are included in scope.
- [x] `V. Minimal Surface, Compatibility, and Security`: MVP constrained to one account, single-host runtime, explicit mode switching, and credential-protection requirements.
- [x] No unresolved gate violations.

Post-Design Re-check (Phase 1):
- [x] Research decisions remove architecture ambiguity and preserve all five principles.
- [x] Data model and contracts maintain testability and traceability to functional requirements.
- [x] No constitution exceptions required.

## Project Structure

### Documentation (this feature)

```text
specs/001-moltbook-threads-bot/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── moltbook-source-contract.md
│   └── review-publish-api.yaml
└── tasks.md               # Created in /speckit.tasks
```

### Source Code (repository root)

```text
.
├── src/
│   ├── api/
│   ├── services/
│   ├── workers/
│   ├── models/
│   └── integrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
└── scripts/
```

**Structure Decision**: Single-project backend service layout is selected to
minimize MVP complexity while keeping clear separation between API surface,
business services, worker cycles, and integration adapters.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
