# Feature Specification: Moltbook Threads Curation Bot

**Feature Branch**: `001-moltbook-threads-bot`  
**Created**: 2026-02-24  
**Status**: Draft  
**Input**: User description: "Based on docs/plans/2026-02-24-moltbook-curation-design.md, build a Threads posting bot that automatically finds interesting content on https://www.moltbook.com, scores and filters it with a local LLM, and publishes it to a dedicated Threads account."

## Clarifications

### Session 2026-02-24

- Q: Must publication require manual approval first? → A: Initially, all content requires manual approval; later, only low-risk content can auto-publish while all other content remains manually approved.
- Q: What fixed archive period should be used for unreviewed candidates? → A: 14 days.
- Q: How many Threads publishing accounts should MVP support? → A: One dedicated account.
- Q: What should MVP do when Threads publication fails? → A: Retry a fixed number of times (3); if still failing, mark terminal failure, notify the operator, and retain debug logs.
- Q: What daily candidate processing throughput must MVP guarantee? → A: At least 500 LLM-scored candidates per day (hourly cycles) while maintaining stable operation without persistent backlog.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Automated Candidate Discovery and Ranking (Priority: P1)

As an operator, I need the system to continuously collect public Moltbook
discussions and rank them by human-interest value so that I can focus only on
the most promising content.

**Why this priority**: Without reliable discovery and ranking, no downstream
review or publishing workflow can deliver value.

**Independent Test**: Load a sample of public discussions, run one scoring
cycle, and verify a ranked candidate list is generated with required fields.

**Acceptance Scenarios**:

1. **Given** public discussions are available, **When** a discovery cycle runs,
   **Then** candidate items are collected from configured time windows.
2. **Given** candidates are collected, **When** scoring is executed, **Then**
   each candidate receives value and risk scores plus a final ranking score.
3. **Given** two candidates are semantically near-duplicates, **When** dedup
   runs, **Then** only one candidate remains eligible for publication.

---

### User Story 2 - Reviewer-Centered Filtering Workflow (Priority: P2)

As an operator, I need a review queue that shows high-context summaries,
translation, source links, and risk labels so that I can approve content quickly
with confidence.

**Why this priority**: The operator's review quality controls brand risk and
content value during MVP.

**Independent Test**: Open the review queue and verify that each item includes
draft content, full Chinese translation, risk tags, and source attribution.

**Acceptance Scenarios**:

1. **Given** ranked candidates exist, **When** they enter review queue,
   **Then** only candidates above the review threshold are shown.
2. **Given** a review item is opened, **When** the operator inspects it,
   **Then** the system shows English draft, full Chinese translation, risk tags,
   source link, and capture time.
3. **Given** a candidate is marked as follow-up, **When** it is queued,
   **Then** it includes a rationale for why follow-up is justified now.

---

### User Story 3 - Scheduled Auto-Publishing to Threads (Priority: P3)

As an operator, I need approved items to be automatically scheduled and posted
to a dedicated Threads account so that publishing stays consistent with minimal
manual effort.

**Why this priority**: This delivers the final business outcome: stable account
growth and recurring value posts.

**Independent Test**: Approve a set of items and verify posts are automatically
published according to daily limits and attribution rules.

**Acceptance Scenarios**:

1. **Given** approved candidates exist, **When** scheduler runs, **Then** the
   system prepares a daily publishing plan within configured volume limits.
2. **Given** publishing mode is changed from full-approval to low-risk-auto,
   **When** scheduling and publish routing executes, **Then** only low-risk
   candidates are eligible for automatic publication and all other candidates
   remain manual-review gated.
3. **Given** a candidate is already published, **When** publishing is attempted
   again, **Then** duplicate publication is blocked.
4. **Given** auto-publishing is active, **When** the operator triggers stop
   control, **Then** no new posts are sent until resumed.

---

**Constitution alignment**: Each user story MUST be independently testable and
deliver value on its own. Each story that changes business logic MUST define
unit-test expectations for that logic.

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when there are fewer than the target number of publish-ready
  items in a day?
- How does system handle source pages that become unavailable after scoring?
- What happens when LLM scoring is unavailable or returns incomplete results?
- How does the system behave when multiple candidates are highly similar but not
  exact URL matches?
- If publishing fails, how does the system retry and notify the operator while
  allowing other scheduled items to continue?
- How does the system prevent risky content from bypassing review during load
  spikes?

## Out of Scope *(mandatory)*

- Explicitly list what this change will NOT implement.
- Document deferred work so it does not leak into implementation tasks.

- Real-time conversational interaction with Moltbook users.
- Multi-platform social publishing beyond Threads.
- Multi-account publishing in MVP.
- Fully unreviewed publishing for high-risk content.
- Model retraining, reinforcement learning loops, or custom foundation model
  development.
- Monetization, ad buying, or growth campaign tooling.

## Observability & Operations *(mandatory)*

- **Logging**: Candidate ingestion outcomes, scoring completion, dedup decisions,
  review actions, scheduling decisions, publish results, and stop/resume events
  MUST be logged with timestamps.
- **Metrics**: Candidate volume, review queue size, approval rate, publish count,
  duplicate-block rate, follow-up rate, and failure rate MUST be tracked.
- **Alerting**: Operators MUST be notified when publish failures exceed threshold,
  queue backlog exceeds daily review cap, or scoring cycles repeatedly fail.
  Final publish failures after retry exhaustion MUST generate immediate operator
  notification through a configured channel.
- **Rollout/Rollback**: The system MUST support controlled activation, immediate
  publish pause, and safe resume without losing approved inventory state.

## Test Strategy *(mandatory)*

- **Unit Tests**: Candidate scoring math, risk penalty behavior, dedup logic,
  follow-up eligibility rules, queue routing thresholds, and publish gating MUST
  have unit tests.
- **Integration Tests**: End-to-end flow from candidate ingestion to approved
  scheduling and publish outcome recording MUST have integration coverage.
- **Contract Tests**: External service contracts for content source retrieval and
  social publishing requests MUST be validated for request/response expectations.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST ingest publicly visible Moltbook discussions on a
  recurring schedule and support configurable source windows (`all time`, `year`,
  `month`, `week`, `today`, `past hour`), with a default hourly processing
  cycle in MVP. Source ingestion in MVP MUST use Moltbook API access patterns
  (per `https://www.moltbook.com/skill.md`) and MUST NOT rely on HTML scraping.
- **FR-002**: System MUST compute a candidate content score using novelty, depth,
  tension, and reflective impact dimensions, plus engagement and risk signals.
- **FR-003**: System MUST route candidates using explicit thresholds for
  low-risk fast track, normal review queue, and priority risk review.
- **FR-004**: System MUST prevent duplicate publication by blocking already
  published source URLs and semantically near-identical content without new
  insight.
- **FR-005**: System MUST support qualified follow-up publication only when
  meaningful new developments exist and follow-up policy constraints are met.
- **FR-006**: System MUST present reviewers with English draft content, full
  sentence-by-sentence Chinese translation, risk tags, source link, and capture
  time for each review item.
- **FR-007**: System MUST allow operators to approve, reject, archive, and pause
  publishing, with all actions recorded for traceability.
- **FR-008**: System MUST automatically schedule and publish approved posts to a
  single dedicated Threads account (MVP scope) within configured daily volume
  limits.
- **FR-009**: System MUST include source attribution link in every published
  Threads post.
- **FR-010**: System MUST archive unreviewed items after 14 days and produce a
  periodic high-score recall list for reconsideration.
- **FR-011**: System MUST retain state for candidate lifecycle transitions
  (`seen`, `scored`, `queued`, `reviewed`, `approved`, `scheduled`, `published`,
  `rejected`, `archived`).
- **FR-012**: System MUST support two publishing modes: `manual-approval` (all
  content requires human approval) and `low-risk-auto` (only low-risk content
  can auto-publish while all other content remains manual-review gated).
- **FR-013**: System MUST require explicit operator action to switch publishing
  mode and MUST log mode-change events for auditability.
- **FR-014**: System MUST validate inputs from source and operator actions, and
  MUST protect sensitive account credentials and tokens from exposure.
- **FR-015**: Changes to scoring, routing, deduplication, publish-gating, and
  mode-switch business logic MUST include corresponding unit tests before merge.
- **FR-016**: When a publish attempt fails, the system MUST retry that item up
  to 3 times before marking the publish job as failed, without blocking other
  eligible publish jobs in the same schedule window.
- **FR-017**: When a publish job reaches terminal failure after retries, the
  system MUST notify the operator through a configured notification channel
  (such as email) and MUST record structured failure details for debugging.
- **FR-018**: In MVP mode, the system MUST support processing at least 500
  candidates per day across hourly cycles without persistent queue backlog.

### Key Entities *(include if feature involves data)*

- **CandidatePost**: A normalized representation of a Moltbook discussion item,
  including source URL, source window, capture time, author handle (if visible),
  raw content snapshot, and lifecycle status.
- **ScoreCard**: A structured scoring record containing novelty, depth, tension,
  reflective impact, engagement, risk, final score, and scoring timestamp.
- **ReviewItem**: A reviewer-facing item with English draft, Chinese full
  translation, risk tags, source attribution, follow-up rationale, and decision.
- **PublishJob**: A scheduled publication task containing target publish time,
  account target, status, retry history, and failure reason (if any).
- **PublishedPostRecord**: Immutable publication evidence including source link,
  published post reference, publish time, and duplicate-control keys.
- **FollowUpCandidate**: A candidate tied to a previously published topic with
  recorded novelty delta and policy eligibility check results.

## Assumptions

- Moltbook content targeted by this feature is publicly viewable and eligible
  for lawful indexing and summarization.
- Moltbook API access described in `https://www.moltbook.com/skill.md` is
  available for this integration.
- The operator provides and controls one dedicated Threads account for this
  automation workflow.
- The operator prefers growth-plus-quality balance and accepts human review as a
  core MVP control.
- Initial rollout uses `manual-approval` mode; migration to `low-risk-auto`
  mode happens only after operator validation.
- The operator provides at least one valid notification endpoint for publish
  failure alerts.
- MVP capacity target is 500 scored candidates per day, with hourly cycle
  execution under normal operating conditions.
- The system may publish between 0 and 5 posts per day depending on approved
  content quality and availability.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: At least 95% of ingestion cycles produce a scored candidate set
  within 60 minutes of cycle start.
- **SC-002**: 100% of published posts include a valid source attribution link.
- **SC-003**: Duplicate publication rate stays below 1% of total published posts
  in a rolling 30-day period.
- **SC-004**: Median reviewer handling time per queue item is under 45 seconds
  when reviewing the daily recommended queue.
- **SC-005**: At least 80% of days with active approved inventory publish at
  least one Threads post.
- **SC-006**: High-risk items (priority review category) reach 100% manual
  review before publication.
- **SC-007**: 100% of terminal publish failures trigger operator notification
  within 5 minutes of final failed attempt.
- **SC-008**: The system successfully scores at least 500 candidates per day in
  normal operation, and no hourly processing cycle backlog persists for more
  than one consecutive cycle.
