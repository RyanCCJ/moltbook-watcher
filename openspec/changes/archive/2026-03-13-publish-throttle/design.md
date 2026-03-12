## Context

The `PublishWorker` currently has a straightforward loop: each `run_cycle()` call schedules all approved candidates with `scheduled_for = now`, then immediately processes every due job in sequence. There is no inter-job delay, no per-cycle cap, and the `max_publish_per_day` setting (defined in `Settings`) is never checked.

The Threads API allows 250 posts per 24-hour rolling window, which is generous. However, the real concern is content distribution — posting 5 articles in 30 seconds means 23.5 hours of silence, making it impossible to analyze per-post engagement or spread reach across time zones.

Key components involved:
- `PublishWorker` — orchestrates scheduling and execution of publish jobs
- `PublishJobRepository` — persists jobs with `scheduled_for` timestamps
- `PublishedPostRecordRepository` — tracks successfully published posts
- `PublishControlService` — guards publish eligibility (mode + pause state)
- `Settings` — holds `max_publish_per_day` (currently capped at 5) and `publish_poll_minutes` (5 min)

## Goals / Non-Goals

**Goals:**
- Enforce `max_publish_per_day` as a hard daily cap based on actual published records
- Space posts evenly across the day using a configurable cooldown (default: 240 minutes ≈ 4 hours)
- Prevent burst publishing by limiting each cycle to at most 1 published post
- Maintain backward compatibility — the `/publish` Telegram command and scheduler both continue to work, just throttled

**Non-Goals:**
- Querying Threads' `threads_publishing_limit` endpoint (overkill for our volume)
- Time-of-day scheduling (e.g., "only publish between 8am–10pm") — can be added later
- Changing the scheduler interval (`publish_poll_minutes`) — keep it at 5 min for responsiveness

## Decisions

### Decision 1: Stagger at scheduling time, not execution time

**Choice**: When multiple candidates are approved, assign each a `scheduled_for` time offset by `cooldown_minutes` from the previous one.

**Alternatives considered**:
- *Inter-job sleep in `run_cycle()`*: Would block the worker for hours; breaks the scheduler model
- *Rate limiter wrapper on `ThreadsClient`*: Adds complexity at the wrong layer; throttling is a business concern, not an API concern

**Rationale**: By staggering `scheduled_for`, the existing `list_due(now)` query naturally returns jobs only when their time arrives. The scheduler (every 5 min) just picks up whatever is due — no new coordination needed.

### Decision 2: Anchor stagger to the latest existing scheduled job

**Choice**: When scheduling new candidates, query the latest `scheduled_for` among existing `scheduled` jobs. New jobs start from `max(now, latest_scheduled) + cooldown`.

**Rationale**: If a user approves 3 posts at 10:00 (yielding jobs at 10:00, 14:00, 18:00), then approves 1 more at 11:00, the new job should go to 22:00 — not 11:00 (which would cluster with the first batch).

### Decision 3: Daily cap checked via `PublishedPostRecordRepository`

**Choice**: Count records in `published_post_records` where `published_at >= now - 24h`. This is the source of truth for actual published output.

**Alternatives considered**:
- *Count `PublishJob` with `status=published`*: Jobs may be recycled or cancelled; records are immutable truth
- *In-memory counter*: Resets on restart; not reliable

### Decision 4: Single job per cycle

**Choice**: After scheduling, `run_cycle()` fetches all due jobs but processes only the first one. Remaining due jobs will be picked up in subsequent cycles (every 5 minutes).

**Rationale**: Combined with staggered scheduling, this is belt-and-suspenders — even if multiple jobs happen to be due simultaneously (e.g., after downtime), only one fires per cycle. This prevents burst publishing in edge cases.

### Decision 5: Cooldown defaults to 240 minutes

**Choice**: `PUBLISH_COOLDOWN_MINUTES=240` as the default, aligning with the user's target of ~6 posts/day spread over 24 hours (24*60/6 = 240).

**Rationale**: This is conservative and allows for organic spread. Users can override via `.env` for tighter schedules during testing.

## Risks / Trade-offs

- **Stale queue after downtime**: If the worker is down for 12 hours, multiple jobs may be due when it restarts. Mitigation: Single-job-per-cycle ensures they trickle out at 5-minute intervals instead of bursting. → Acceptable.
- **Scheduling drift**: If `_schedule_approved_candidates` is called every cycle (every 5 min), it re-checks for approved candidates each time. Existing filter (`notin_(existing_candidate_ids)`) prevents duplicates. → No issue.
- **`max_publish_per_day` mismatch with cooldown**: If `max_publish_per_day=6` but `cooldown=60min`, the daily cap would be hit before cooldown space runs out. → The daily cap is the hard limit; cooldown is the soft spacer. Both apply independently.
