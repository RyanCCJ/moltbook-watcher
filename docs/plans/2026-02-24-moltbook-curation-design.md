# Moltbook Curation to Threads Design (MVP)

Date: 2026-02-24  
Status: Draft (Approved for planning)

## 1. Problem and Goal

Build a content pipeline that monitors public Moltbook discussions, uses a local
LLM to surface meaningful threads, and publishes curated content to Threads
with low operator workload and controlled risk.

Primary goals:
- Keep daily effort low (review queue recommendation cap: 10/day).
- Maintain stable output (scheduler target: 3/day, flexible 0-5/day).
- Prioritize human-interest and thought-provoking AI discussions.
- Enforce attribution (every published post includes source link).
- Keep MVP easy to develop and validate on one machine.

## 2. Scope

In scope:
- Public Moltbook content ingestion.
- Scoring, routing, deduplication, review queue, scheduling, and publishing flow.
- Assist-mode operation with optional future Shadow/Guarded Auto modes.
- Single-host runtime architecture for fast iteration.

Out of scope (MVP):
- Deploying pipeline services to Kubernetes.
- Full autonomous publishing without operator override.
- Non-Moltbook source integrations.
- Advanced ML retraining pipeline.

## 3. Key Product Decisions

- Mode: `Assist` (human review centered), reversible to `Shadow` and future
  `Guarded Auto`.
- Language: publish in English; provide full sentence-by-sentence Chinese
  translation for review.
- Daily output: flexible `0-5`, scheduler target `3`.
- Review: async, queue recommendation cap `10/day`.
- Source policy: public content only; every published post must include source
  URL.
- Dedup policy: same source URL/thread is never reposted as new.
- Similarity block: semantic similarity `>= 90%` with no new insight is blocked.

## 4. MVP Runtime Topology (No k8s Deployment)

All application services run on the local Mac host for MVP.

```text
Mac Studio M4 Max (48GB)
├─ Ollama (local inference)
│  └─ model: Qwen3-VL-4B (MVP default)
├─ Pipeline Worker (single service)
├─ Review Dashboard (local web app)
├─ Redis (local queue/cache)
└─ PostgreSQL (local source-of-truth)
```

Why this topology:
- Fastest development loop for prompt and scoring changes.
- Shortest debugging path.
- No Kubernetes deployment complexity during MVP.
- Sufficient for expected throughput.

## 5. End-to-End Flow

```text
Fetch -> Normalize -> Dedup -> Score -> Route -> Review -> Schedule -> Publish
                                       |                             |
                                       +-> Archive/Reject            +-> Log + State
```

State transitions:

```text
candidate -> seen -> scored -> queued -> reviewed
                                    |-> approved -> scheduled -> published
                                    |-> rejected
unreviewed (14 days) -> archived -> weekly high-score recall list
```

## 6. Scoring Model

### 6.1 ContentScore

`ContentScore = 0.20*Novelty + 0.35*Depth + 0.20*Tension + 0.25*ReflectiveImpact`

Dimensions:
- Novelty: uncommon or counter-intuitive angle.
- Depth: reasoning quality, not slogans.
- Tension: value-conflict relevance.
- ReflectiveImpact: likely to trigger human reflection.

### 6.2 FinalScore

`FinalScore = 0.6*ContentScore + 0.4*Engagement - RiskPenalty`

Risk penalty policy:
- Risk = 2: -0.10
- Risk = 3: -0.25
- Risk >= 4: force priority human review

## 7. Routing Rules

Low-Risk Fast Track:
- `FinalScore >= 4.0` and `Risk <= 1`
- In Assist mode, still remains human-confirmable before final publish.

Human review queue admission:
- `FinalScore >= 3.5`

Hard moderation gate:
- Policy-unsafe content is blocked from publish route.

## 8. Dedup and Follow-up Policy

Dedup:
- Same source URL/thread ID: never republish as new.
- Semantic similarity >= 90% and no new insight: block.

Qualified follow-up:
- Allowed only with meaningful new developments.
- Same-topic minimum interval: 7 days.
- Max 1 follow-up per day.
- Must include one-line justification: `Why follow-up now`.

## 9. Time-Driven Source Strategy

Week 1:
- Source mix: `all time 80% + month 20%`
- Daily output: `0-5`

Week 2:
- Source mix: `month 50% + week 30% + today 20%`
- Daily output: `0-5`

Week 3+:
- Source mix: `(today + past hour) 70% + (week + month) 30%`
- Daily output: `0-5` (scheduler target remains 3/day)

## 10. Review UX Requirements

Each review item must show:
- English draft (to publish)
- Full Chinese sentence-by-sentence translation
- Risk tags
- Source URL and capture timestamp
- Follow-up justification (if follow-up candidate)

## 11. Publishing and Cadence

- New content first; follow-up only as gap-fill.
- If approved items exceed daily budget, defer to inventory (no content loss).
- If fresh items are insufficient, backfill with approved inventory.
- Queue recommendation cap for operator: 10/day.

## 12. Reliability and Operations Runbook

Process supervision:
- Run pipeline service under `launchd` (not interactive terminal sessions).
- Auto-restart on failure.

Job safety:
- Every stage must be idempotent.
- Publish action must check final dedup guard before sending.

Failure handling:
- Retries with capped backoff for transient errors.
- Dead-letter queue for repeated failures.

Data safety:
- Daily PostgreSQL backup/snapshot.
- Retain event logs for audit and debugging.

Operator controls:
- Kill switch to pause publishing.
- Reversible mode transitions (`Assist <-> Shadow <-> Guarded Auto`).
- Weekly archived high-score recall report.

## 13. Observability

Track at minimum:
- Candidate volume by source window.
- Queue volume, review throughput, and backlog age.
- Approval/rejection rates by risk band.
- Published count/day and source mix ratio.
- Follow-up acceptance rate.
- Duplicate block rate and semantic-block reasons.
- Pipeline stage latency and LLM timeout rates.

## 14. Testing Strategy (Planning-Level)

Core verification areas:
- Scoring consistency for representative examples.
- Routing threshold correctness (Fast Track vs Review Queue).
- Dedup correctness (URL and semantic near-duplicate).
- Follow-up gate correctness (7-day cooldown + new-development requirement).
- Scheduler behavior under underflow/overflow.
- Translation completeness in review payload.
- Idempotent publish guard.

## 15. Future Evolution

Planned but optional:
- Shadow-mode calibration before enabling more automation.
- Guarded Auto for low-risk candidates only.
- Dynamic slot optimization from account interaction history.
- Optional migration of queue/store layers to existing Kubernetes services
  after MVP stabilizes.

## 16. Acceptance Criteria for MVP Design

- End-to-end flow is fully specified with routing and risk controls.
- Runtime architecture is single-host and does not require k8s deployment.
- Review workload remains bounded by daily recommendation cap.
- Content strategy supports short-term growth and long-term value.
- No-duplicate and qualified-follow-up behaviors are explicit and testable.

## 17. Implementation Update (2026-02-25)

Implemented in this repository:
- FastAPI API bootstrap with health, review, and publish endpoints.
- SQLAlchemy models for candidate, scoring, review, publish job, published
  record, follow-up candidate, and notification event entities.
- Worker logic for ingestion, publish retries, and archive/recall processing.
- Source adapter and Threads adapter abstractions.
- Unit, contract, integration, throughput, and E2E smoke tests aligned with the
  MVP acceptance path.

Validation summary:
- US1 tests: scoring/dedup/source contract/ingestion integration passing.
- US2 tests: routing/review contract/review lifecycle integration passing.
- US3 tests: publish mode/retry policy/publish contract/publish integration
  passing.
- Polish tests: end-to-end smoke, throughput SLA, and security redaction checks
  passing.
