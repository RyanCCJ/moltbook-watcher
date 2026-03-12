# Capability: Publish Throttle

## Purpose
Rate-limit the publish pipeline to prevent burst publishing, enforce daily caps, and distribute posts evenly across the day.

## ADDED Requirements

### Requirement: Daily publish cap enforcement
The `PublishWorker` SHALL check the number of posts published in the last 24 hours (rolling window) before processing any jobs. If the count is greater than or equal to `max_publish_per_day`, the cycle SHALL skip all job processing and return immediately.

#### Scenario: Daily cap not yet reached
- **WHEN** 4 posts have been published in the last 24 hours and `max_publish_per_day=6`
- **THEN** the publish cycle SHALL proceed to process due jobs

#### Scenario: Daily cap reached
- **WHEN** 6 posts have been published in the last 24 hours and `max_publish_per_day=6`
- **THEN** the publish cycle SHALL return immediately with zero processed jobs

### Requirement: Single job per cycle
Each invocation of `PublishWorker.run_cycle()` SHALL process at most one due publish job. If multiple jobs are due, only the earliest-created job SHALL be processed; remaining jobs SHALL be left for subsequent cycles.

#### Scenario: Multiple due jobs
- **WHEN** 3 publish jobs are due at the current time
- **THEN** the cycle SHALL process only the first job and return, leaving the other 2 for future cycles

#### Scenario: No due jobs
- **WHEN** no publish jobs have `scheduled_for <= now`
- **THEN** the cycle SHALL return with zero processed jobs

### Requirement: Staggered scheduling of approved candidates
When `PublishWorker` schedules approved candidates into publish jobs, each successive candidate SHALL have its `scheduled_for` time offset by `publish_cooldown_minutes` from the previous one. The first candidate's `scheduled_for` SHALL be set to `max(now, latest_existing_scheduled_job_time + cooldown)`.

#### Scenario: First approved candidate with no existing scheduled jobs
- **WHEN** 1 approved candidate exists and no publish jobs are currently scheduled
- **THEN** the candidate SHALL be scheduled with `scheduled_for = now`

#### Scenario: Multiple approved candidates with no existing scheduled jobs
- **WHEN** 3 approved candidates exist, no existing scheduled jobs, and `publish_cooldown_minutes=240`
- **THEN** candidates SHALL be scheduled at `now`, `now + 240min`, and `now + 480min`

#### Scenario: New candidate with existing scheduled jobs
- **WHEN** 1 approved candidate exists, an existing scheduled job has `scheduled_for = 18:00`, and `publish_cooldown_minutes=240`
- **THEN** the new candidate SHALL be scheduled at `22:00` (18:00 + 240min)

### Requirement: Configurable cooldown interval
The system SHALL support a `PUBLISH_COOLDOWN_MINUTES` environment variable that controls the minimum time interval between successive publish jobs. The default value SHALL be `240` (4 hours).

#### Scenario: Default cooldown
- **WHEN** `PUBLISH_COOLDOWN_MINUTES` is not set in `.env`
- **THEN** the system SHALL use 240 minutes as the cooldown interval

#### Scenario: Custom cooldown
- **WHEN** `PUBLISH_COOLDOWN_MINUTES=60` is set in `.env`
- **THEN** the system SHALL space publish jobs 60 minutes apart

### Requirement: Published post count query
`PublishedPostRecordRepository` SHALL provide a `count_since(session, since)` method that returns the number of records with `published_at >= since`.

#### Scenario: Count published in last 24 hours
- **WHEN** 3 records have `published_at` within the last 24 hours and 2 records are older
- **THEN** `count_since(now - 24h)` SHALL return `3`

### Requirement: Latest scheduled job query
`PublishJobRepository` SHALL provide a `get_latest_scheduled_time(session)` method that returns the maximum `scheduled_for` value among jobs with `status = "scheduled"`, or `None` if no scheduled jobs exist.

#### Scenario: Scheduled jobs exist
- **WHEN** 3 scheduled jobs exist with `scheduled_for` at 10:00, 14:00, 18:00
- **THEN** `get_latest_scheduled_time()` SHALL return `18:00`

#### Scenario: No scheduled jobs
- **WHEN** no jobs have `status = "scheduled"`
- **THEN** `get_latest_scheduled_time()` SHALL return `None`
