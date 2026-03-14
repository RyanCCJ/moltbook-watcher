# Data Model: Moltbook Threads Curation Bot

## Overview

This model defines core entities for candidate ingestion, scoring, review,
scheduling, publishing, follow-up eligibility, and operational auditing.

## Entities

### CandidatePost

- Purpose: Canonical record of source content discovered from Moltbook.
- Key fields:
  - `id` (UUID, primary key)
  - `source_url` (string, required)
  - `source_window` (enum: all_time|year|month|week|today|past_hour)
  - `source_post_id` (string, optional but unique when present)
  - `author_handle` (string, optional)
  - `raw_content` (text, required)
  - `captured_at` (timestamp, required)
  - `status` (enum: seen|scored|queued|reviewed|approved|scheduled|published|rejected|archived)
  - `dedup_fingerprint` (string, required)
  - `is_follow_up_candidate` (boolean, default false)
- Validation rules:
  - `source_url` must be valid absolute URL.
  - `raw_content` must be non-empty.
  - `status` transitions must follow lifecycle rules.
- Identity and uniqueness:
  - Unique constraint on `source_url` for published items.
  - Unique constraint on `dedup_fingerprint` for active queue scope.

### ScoreCard

- Purpose: Persist model scoring output for each candidate.
- Key fields:
  - `id` (UUID, primary key)
  - `candidate_post_id` (UUID, FK -> CandidatePost.id)
  - `novelty_score` (decimal 0-5)
  - `depth_score` (decimal 0-5)
  - `tension_score` (decimal 0-5)
  - `reflective_impact_score` (decimal 0-5)
  - `engagement_score` (decimal 0-5)
  - `risk_score` (integer 0-5)
  - `content_score` (decimal 0-5)
  - `final_score` (decimal 0-5)
  - `score_version` (string)
  - `scored_at` (timestamp)
- Validation rules:
  - All score fields constrained to expected ranges.
  - `final_score` must be derived from configured formula.

### ReviewItem

- Purpose: Operator-facing review payload and decision record.
- Key fields:
  - `id` (UUID, primary key)
  - `candidate_post_id` (UUID, FK)
  - `english_draft` (text, required)
  - `chinese_translation_full` (text, required)
  - `risk_tags` (array<string>)
  - `follow_up_rationale` (text, optional)
  - `decision` (enum: pending|approved|rejected|archived)
  - `reviewed_by` (string, optional)
  - `reviewed_at` (timestamp, optional)
- Validation rules:
  - `chinese_translation_full` required before decision submission.
  - `follow_up_rationale` required when follow-up flag is true.

### PublishJob

- Purpose: Track scheduled and attempted publication execution.
- Key fields:
  - `id` (UUID, primary key)
  - `candidate_post_id` (UUID, FK)
  - `threads_account_key` (string, required)
  - `scheduled_for` (timestamp, required)
  - `status` (enum: scheduled|in_progress|published|failed_terminal|cancelled)
  - `attempt_count` (integer, default 0)
  - `max_attempts` (integer, default 3)
  - `last_error_code` (string, optional)
  - `last_error_message` (text, optional)
  - `updated_at` (timestamp)
- Validation rules:
  - `attempt_count <= max_attempts`.
  - Terminal state required after max attempts reached.

### PublishedPostRecord

- Purpose: Immutable publication ledger and duplicate guard source.
- Key fields:
  - `id` (UUID, primary key)
  - `candidate_post_id` (UUID, FK)
  - `source_url` (string, required)
  - `threads_post_id` (string, required)
  - `published_at` (timestamp, required)
  - `attribution_link` (string, required)
- Validation rules:
  - `threads_post_id` must be unique.
  - `source_url` can only appear once for non-follow-up publish type.

### FollowUpCandidate

- Purpose: Capture eligibility and novelty delta for follow-up content.
- Key fields:
  - `id` (UUID, primary key)
  - `candidate_post_id` (UUID, FK)
  - `prior_published_post_id` (UUID, FK -> PublishedPostRecord.id)
  - `novelty_delta_score` (decimal 0-5)
  - `justification` (text, required)
  - `eligible_after` (timestamp, required)
  - `is_eligible` (boolean)
- Validation rules:
  - `eligible_after` must be >= prior publish + 7 days.
  - `justification` required when `is_eligible = true`.

### NotificationEvent

- Purpose: Record operator alerts for terminal publish failures.
- Key fields:
  - `id` (UUID, primary key)
  - `publish_job_id` (UUID, FK)
  - `channel` (enum: smtp_email)
  - `recipient` (string, required)
  - `status` (enum: pending|sent|failed)
  - `sent_at` (timestamp, optional)
  - `error_message` (text, optional)

## Relationships

- CandidatePost 1:1 ScoreCard (latest score for current version).
- CandidatePost 1:1 ReviewItem (current review payload).
- CandidatePost 1:N PublishJob (reschedules/retries tracked per job lifecycle).
- CandidatePost 0..1 PublishedPostRecord (non-follow-up publish record).
- PublishedPostRecord 0..N FollowUpCandidate (future follow-up opportunities).
- PublishJob 0..N NotificationEvent (attempted notifications).

## Lifecycle and State Transitions

### CandidatePost

- `seen -> scored -> queued -> reviewed`
- `reviewed -> approved -> scheduled -> published`
- `reviewed -> rejected`
- `queued -> archived` (after 14 days without review)

Transition constraints:
- Cannot move to `scheduled` unless review decision is approved.
- Cannot move to `published` without successful PublishJob terminal success.
- Cannot re-enter `queued` from `published` except through FollowUpCandidate path.

### PublishJob

- `scheduled -> in_progress -> published`
- `in_progress -> scheduled` (retry scheduling while attempts remain)
- `in_progress -> failed_terminal` (after max attempts)
- Any non-terminal state -> `cancelled` by operator pause/kill switch.

## Scale Assumptions

- Candidate volume: up to 500 scored candidates/day.
- Review recommendation volume: up to 10/day.
- Publish volume: 0-5/day.
- One operator, one Threads account for MVP.
