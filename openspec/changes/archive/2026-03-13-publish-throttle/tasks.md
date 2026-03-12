## 1. Configuration

- [x] 1.1 Add `publish_cooldown_minutes: int = 240` to `Settings` in `src/config/settings.py` with validator `>= 0`
- [x] 1.2 Relax `max_publish_per_day` validator from max=5 to max=10 in `src/config/settings.py`
- [x] 1.3 Add `PUBLISH_COOLDOWN_MINUTES` and updated `MAX_PUBLISH_PER_DAY` to `.env.example` with comments

## 2. Repository Methods

- [x] 2.1 Add `count_since(session, since: datetime) -> int` to `PublishedPostRecordRepository` in `src/models/published_post_record.py`
- [x] 2.2 Add `get_latest_scheduled_time(session) -> datetime | None` to `PublishJobRepository` in `src/models/publish_job.py`

## 3. PublishWorker Throttle Logic

- [x] 3.1 Accept `max_publish_per_day` and `cooldown_minutes` parameters in `PublishWorker.__init__`
- [x] 3.2 Add daily cap check at the start of `run_cycle()` — query `PublishedPostRecordRepository.count_since(now - 24h)` and return early if at cap
- [x] 3.3 Modify `_schedule_approved_candidates()` to stagger `scheduled_for` using cooldown interval, anchored to the latest existing scheduled job time
- [x] 3.4 Limit `run_cycle()` to process at most 1 due job (take first from `list_due`, ignore rest)

## 4. Runtime Wiring

- [x] 4.1 Pass `max_publish_per_day` and `publish_cooldown_minutes` from settings to `PublishWorker` in `run_publish_once()` in `src/workers/runtime.py`

## 5. Tests

- [x] 5.1 Test `PublishedPostRecordRepository.count_since` returns correct count
- [x] 5.2 Test `PublishJobRepository.get_latest_scheduled_time` returns max time or None
- [x] 5.3 Test `run_cycle` skips processing when daily cap is reached
- [x] 5.4 Test `_schedule_approved_candidates` staggers jobs by cooldown interval
- [x] 5.5 Test `_schedule_approved_candidates` anchors to latest existing scheduled job
- [x] 5.6 Test `run_cycle` processes at most 1 job per cycle even when multiple are due
