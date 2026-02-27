<!--
Sync Impact Report
- Version change: 1.0.0 -> 1.1.0
- Modified principles:
  - III. Test-First Verification -> III. Test-First Verification and Unit Coverage
- Added sections:
  - None
- Removed sections:
  - None
- Templates requiring updates:
  - ✅ updated: .specify/templates/plan-template.md
  - ✅ updated: .specify/templates/spec-template.md
  - ✅ updated: .specify/templates/tasks-template.md
  - ⚠ pending: .specify/templates/commands/*.md (directory not present; no files to validate)
- Runtime guidance docs:
  - ✅ checked: docs/plans/2026-02-24-moltbook-curation-design.md (no constitution reference change required)
- Follow-up TODOs:
  - None
-->
# Moltbook Watcher Constitution

## Core Principles

### I. Spec-Driven Delivery (NON-NEGOTIABLE)
Every implementation change MUST trace to an approved spec artifact set
(`spec.md`, `plan.md`, `tasks.md`) before coding begins. Plans MUST include a
passed Constitution Check both before research and after design. Untracked code
changes are non-compliant and MUST be rejected in review.
Rationale: Traceability prevents drift between intent and implementation.

### II. Independently Valuable Increments
Specifications MUST define prioritized user stories (P1, P2, P3...) where each
story is independently testable and can deliver user value on its own. Tasks
MUST be grouped by story and preserve the ability to ship incrementally without
requiring completion of all lower-priority work.
Rationale: Independent increments reduce delivery risk and improve feedback
quality.

### III. Test-First Verification and Unit Coverage
For each user story, verification tasks MUST be defined before implementation
tasks and MUST fail before implementation starts. Every merged change MUST
include automated evidence for the impacted behavior (unit, integration, or
contract tests as appropriate), plus explicit regression coverage for defects.
Each change that introduces or modifies business logic MUST include unit tests
for that logic, covering both expected paths and relevant edge cases.
Rationale: Test-first discipline catches requirement and design errors early,
and unit tests provide fast, deterministic protection against regressions.

### IV. Operability and Traceability
Every feature specification MUST define observable behavior, including logging,
error handling expectations, and measurable success criteria. Plans and tasks
MUST include rollout/rollback considerations for user-impacting changes. Each
requirement MUST map forward to implementation and verification artifacts.
Rationale: Observable systems are faster to debug, safer to operate, and easier
to maintain.

### V. Minimal Surface, Compatibility, and Security
Changes MUST use the smallest viable design that satisfies current requirements.
Breaking behavior, API contract changes, and data migrations MUST include a
documented migration path and explicit versioning impact. Inputs MUST be
validated and sensitive data MUST NOT be exposed in logs, tests, or fixtures.
Rationale: Small, compatible, and secure changes lower operational and product
risk.

## Engineering Constraints

- Artifact authority: spec artifacts under `specs/` and `.specify/`
  templates are the planning source of truth.
- Language/tool neutrality: templates MUST remain technology-agnostic unless a
  concrete project stack has been formally documented.
- Documentation quality: normative instructions MUST use explicit terms (`MUST`,
  `SHOULD`, `MUST NOT`) and avoid ambiguous guidance.

## Workflow and Quality Gates

1. Define or update spec artifacts before implementation.
2. Pass Constitution Check in `plan.md` before Phase 0 research.
3. Re-run Constitution Check after design updates in `plan.md`.
4. Build `tasks.md` with test-first ordering per user story.
5. Implement tasks in priority order while preserving independent story
   testability.
6. Before merge, verify requirement-to-test traceability and document any
   justified constitution exceptions in Complexity Tracking, including explicit
   unit-test coverage for changed business logic.

## Governance

This constitution overrides conflicting local conventions for planning and
delivery workflows.

Amendment procedure:
1. Propose amendments in `.specify/memory/constitution.md` with rationale and
   impacted templates/docs.
2. Review the proposal with maintainers responsible for delivery workflow.
3. Apply required template and guidance updates in the same change.
4. Update the Sync Impact Report at the top of this file.

Versioning policy:
- MAJOR: incompatible changes to governance model or removal/redefinition of a
  core principle.
- MINOR: new principle/section or materially expanded mandatory guidance.
- PATCH: clarifications, wording improvements, typo fixes, or non-semantic
  refinements.

Compliance review expectations:
- Every implementation plan MUST include a Constitution Check with explicit
  pass/fail status per principle.
- Every pull request MUST show evidence that relevant tests passed and that
  observability/security impacts were addressed.
- Every pull request that changes business logic MUST include or update unit
  tests for that logic, or document an approved exception.
- Exceptions MUST be documented in the plan's Complexity Tracking section with
  rationale and approval.

**Version**: 1.1.0 | **Ratified**: 2026-02-23 | **Last Amended**: 2026-02-24
