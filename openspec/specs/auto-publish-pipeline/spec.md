# Capability: Auto-publish Pipeline

## Purpose
Enable a semi-auto publish path where qualified high-score, low-risk posts can bypass human review.

## Requirements

### Requirement: Semi-auto publish mode
The `PublishMode` enum SHALL replace `LOW_RISK_AUTO` with `SEMI_AUTO`. The `publish_mode` setting SHALL accept `"semi-auto"` as a valid value. The previous value `"low-risk-auto"` SHALL no longer be accepted.

#### Scenario: PUBLISH_MODE set to semi-auto
- **WHEN** `PUBLISH_MODE=semi-auto` is configured in `.env`
- **THEN** the system SHALL enable the semi-auto publish path

#### Scenario: Legacy low-risk-auto value rejected
- **WHEN** `PUBLISH_MODE=low-risk-auto` is configured in `.env`
- **THEN** the application SHALL fail at startup with a validation error

### Requirement: Auto-approve for qualifying posts
When `PUBLISH_MODE=semi-auto`, posts that meet both `final_score >= AUTO_PUBLISH_MIN_SCORE` and `risk_score <= 1` (i.e., `RoutingService` returns `fast_track`) SHALL be automatically transitioned from `queued` to `approved` without human review.

#### Scenario: Post qualifies for auto-approve
- **WHEN** `PUBLISH_MODE=semi-auto` and a post has `final_score=4.2` and `risk_score=1` and RoutingService returns `fast_track`
- **THEN** the candidate SHALL transition `queued → approved` without waiting for human review

#### Scenario: Post does not qualify for auto-approve
- **WHEN** `PUBLISH_MODE=semi-auto` and a post has `final_score=3.8` and `risk_score=1` (below `AUTO_PUBLISH_MIN_SCORE=4.0`)
- **THEN** the candidate SHALL remain in `queued` status and require human review via Telegram

#### Scenario: Manual-approval mode ignores routing
- **WHEN** `PUBLISH_MODE=manual-approval` and a post meets all auto-approve criteria
- **THEN** the candidate SHALL remain in `queued` status and require human review

### Requirement: QUEUED to APPROVED lifecycle transition
The lifecycle state machine SHALL allow the transition `QUEUED → APPROVED` to support the semi-auto publish path. This transition bypasses the `REVIEWED` state.

#### Scenario: Valid QUEUED to APPROVED transition
- **WHEN** a candidate in `queued` status is transitioned to `approved` via the semi-auto path
- **THEN** the transition SHALL succeed without raising an assertion error

### Requirement: ReviewWorker still processes auto-approved posts
Auto-approved posts SHALL still be processed by `ReviewWorker` to generate translation and Threads draft content. The `review_item` SHALL have `decision="approved"` and `reviewed_by="semi-auto"`.

#### Scenario: Auto-approved post gets review item
- **WHEN** a post is auto-approved via the semi-auto path
- **THEN** a `review_item` SHALL be created with translation, Threads draft, `decision="approved"`, and `reviewed_by="semi-auto"`

#### Scenario: PublishWorker uses auto-approved draft
- **WHEN** `PublishWorker` picks up an auto-approved candidate
- **THEN** it SHALL use the `threads_draft` from the associated `review_item`, same as manually approved posts

### Requirement: PublishControlService updated for semi-auto
The `PublishControlService.can_auto_publish()` method SHALL be called by the pipeline when `PUBLISH_MODE=semi-auto`. The method SHALL check both the publish mode and the `risk_score` threshold. The `MAX_PUBLISH_PER_DAY` setting SHALL accept values between 0 and 10 (previously capped at 5).

#### Scenario: can_auto_publish returns true
- **WHEN** `publish_mode` is `semi-auto`, the system is not paused, and `risk_score <= 1`
- **THEN** `can_auto_publish()` SHALL return `True`

#### Scenario: can_auto_publish when paused
- **WHEN** `publish_mode` is `semi-auto` but publishing is paused
- **THEN** `can_auto_publish()` SHALL return `False`

#### Scenario: max_publish_per_day set to 6
- **WHEN** `MAX_PUBLISH_PER_DAY=6` is configured in `.env`
- **THEN** the application SHALL accept and use the value without validation error
