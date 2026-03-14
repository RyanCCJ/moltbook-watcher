from types import SimpleNamespace

from src.workers import scheduler


def test_build_scheduler_adds_daily_summary_job_when_telegram_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            ingestion_interval_minutes=60,
            publish_poll_minutes=5,
            telegram_enabled=True,
            telegram_chat_id="12345",
            telegram_daily_summary_hour=22,
            telegram_daily_summary_timezone="Asia/Taipei",
        ),
    )

    built_scheduler = scheduler.build_scheduler()
    jobs = built_scheduler.get_jobs()

    assert len(jobs) == 3
    assert any(job.func == scheduler.run_daily_summary_cycle for job in jobs)


def test_build_scheduler_skips_daily_summary_job_when_telegram_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            ingestion_interval_minutes=60,
            publish_poll_minutes=5,
            telegram_enabled=False,
            telegram_chat_id="",
            telegram_daily_summary_hour=22,
            telegram_daily_summary_timezone="UTC",
        ),
    )

    built_scheduler = scheduler.build_scheduler()
    jobs = built_scheduler.get_jobs()

    assert len(jobs) == 2
