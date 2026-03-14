## Why

The current `PublishWorker` processes all due publish jobs in a single cycle with no inter-job delay and no daily limit enforcement. When multiple posts are approved (either manually via Telegram or automatically via semi-auto mode), they are all dispatched to the Threads API within seconds. This creates two problems: (1) risk of hitting Threads platform rate limits, and (2) poor content distribution — posts clustered in a short window leave no content for the rest of the day, making traffic analysis ineffective.

## What Changes

- Enforce `max_publish_per_day` (currently defined but unused) as a hard daily cap, checked against actual published records in the last 24 hours
- Add a configurable `publish_cooldown_minutes` setting to space out posts evenly throughout the day (default: 240 minutes = 4 hours)
- Stagger `scheduled_for` times when scheduling multiple approved candidates, so each successive job is offset by the cooldown interval
- Limit each publish cycle to processing at most one due job, relying on the existing scheduler interval to pick up the next job in a future cycle

## Capabilities

### New Capabilities
- `publish-throttle`: Rate-limiting and staggered scheduling for the publish pipeline, including daily cap enforcement, inter-post cooldown, and single-job-per-cycle processing

### Modified Capabilities
- `auto-publish-pipeline`: The PublishWorker scheduling behavior changes — approved candidates are now staggered instead of all scheduled for immediate execution, and the daily cap is actively enforced

## Impact

- **Code**: `PublishWorker`, `PublishRetryPolicy` (or new throttle logic), `PublishedPostRecordRepository`, `Settings`
- **Config**: New `PUBLISH_COOLDOWN_MINUTES` env var; `MAX_PUBLISH_PER_DAY` validator relaxed from max=5 to max=10
- **APIs**: No external API changes; `/publish` Telegram command behavior changes subtly (schedules then processes at most 1)
- **Systems**: Scheduler polling interval (`publish_poll_minutes`) remains unchanged but now cooperates with staggered scheduling
