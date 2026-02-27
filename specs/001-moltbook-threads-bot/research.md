# Research: Moltbook Threads Curation Bot

## Scope

Research decisions cover unresolved implementation choices from technical
context, integration reliability requirements, and operational constraints for a
single-host MVP.

## Decision 1: Runtime stack uses Python 3.12 backend service managed by uv

- Decision: Use Python 3.12 as the primary implementation language and manage
  project dependencies, environment, and command execution with uv.
- Rationale: Python has mature ecosystem support for asynchronous worker
  orchestration, API services, data workflows, and test tooling needed for this
  project, while uv provides fast and consistent local dependency management.
- Alternatives considered:
  - Node.js/TypeScript: Strong async model, but weaker fit for rapid
    experimentation with local LLM scoring and data-processing workflows in this
    project context.
  - Go: Strong runtime efficiency, but slower MVP iteration velocity for this
    feature set.

## Decision 2: Local LLM served via Ollama with Qwen3-VL-4B profile

- Decision: Use local Ollama-hosted Qwen3-VL-4B profile for candidate scoring
  and bilingual review payload generation.
- Rationale: Matches local-host constraint, avoids cloud inference cost, and is
  sufficient for MVP throughput and quality calibration.
- Alternatives considered:
  - Larger local models: Better quality potential, but reduced concurrency and
    higher memory pressure on the same host.
  - Cloud LLM APIs: Faster model updates but violates local-cost and privacy
    preferences.

## Decision 3: Data persistence uses PostgreSQL + Redis split

- Decision: Persist lifecycle entities in PostgreSQL and use Redis for queueing
  and short-lived processing state.
- Rationale: This split provides durable audit history plus low-latency queue
  operations and retry handling.
- Alternatives considered:
  - PostgreSQL only: Simpler architecture but weaker queue ergonomics.
  - Redis only: Fast queueing but poor long-term traceability and reporting.

## Decision 4: Moltbook ingestion uses official API access path from skill guide

- Decision: Read Moltbook content via API interfaces documented in
  `https://www.moltbook.com/skill.md`, not via HTML crawling for MVP.
- Rationale: API-based ingestion is more stable, easier to validate, and aligns
  with the source platform's agent-first integration model.
- Alternatives considered:
  - HTML/web crawling: More brittle, higher maintenance overhead, and weaker
    long-term compatibility with platform changes.

## Decision 5: Publish integration uses official Threads publish interface

- Decision: Integrate with the official Threads publishing interface and token
  model, wrapped behind an internal publish adapter.
- Rationale: Reduces account-risk exposure and keeps contract testing focused on
  stable request/response boundaries.
- Alternatives considered:
  - Browser-driven posting automation: More brittle, harder to maintain, and
    less transparent for failure diagnostics.

## Decision 6: Publish failure handling uses capped retries + terminal alert

- Decision: Retry failed publish attempts up to 3 times with backoff; on
  terminal failure, emit immediate operator notification and record structured
  failure logs.
- Rationale: Balances reliability and operational safety without causing queue
  deadlock or infinite retry loops.
- Alternatives considered:
  - Stop all publishing on first failure: Overly disruptive to daily schedule.
  - Unlimited retries: Risk of runaway loops and delayed operator awareness.

## Decision 7: Scheduling uses hourly ingestion and daily bounded publishing

- Decision: Run ingestion/scoring in hourly cycles and enforce publishing within
  0-5 posts/day target with inventory buffering.
- Rationale: Aligns with spec throughput target (>=500 candidates/day) while
  keeping reviewer workload and posting cadence controlled.
- Alternatives considered:
  - Real-time continuous ingestion: Higher complexity with little MVP benefit.
  - Daily batch-only ingestion: Slower reaction to emerging threads.

## Decision 8: Notification channel starts with SMTP email alerts

- Decision: Use SMTP email as MVP failure notification channel.
- Rationale: Low setup overhead, easy auditability, and straightforward operator
  delivery semantics.
- Alternatives considered:
  - Chat webhook-only notifications: Useful but less universal as first channel.
  - Push-only local notifications: Less reliable for unattended operations.

## Decision 9: Test strategy prioritizes unit coverage of business logic

- Decision: Require unit tests for scoring, routing, deduplication, mode
  switching, and publish gating logic, with integration and contract tests for
  pipeline boundaries.
- Rationale: Satisfies constitution requirements and reduces regression risk in
  fast-iteration MVP cycles.
- Alternatives considered:
  - Integration-first only: Slower feedback for business-rule regressions.
  - Contract-only strategy: Insufficient for internal decision logic.

## Clarification Resolution Summary

All technical-context unknowns are resolved for planning:
- No remaining `NEEDS CLARIFICATION` items.
- Chosen architecture supports constitution gates and measured success criteria.
