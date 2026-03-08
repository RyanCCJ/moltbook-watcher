from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.candidate_post import CandidatePostRepository
from src.models.review_item import ReviewItemRepository
from src.models.score_card import ScoreCardRepository
from src.workers import scheduler


class _StubTelegramClient:
    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token
        self.sent_messages: list[tuple[str, str, dict | None]] = []
        self.closed = False

    async def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict:
        self.sent_messages.append((chat_id, text, reply_markup))
        return {"ok": True}

    async def close(self) -> None:
        self.closed = True


async def _create_review_item(
    session,
    *,
    source_post_id: str,
    captured_at: datetime,
    final_score: float,
) -> None:
    candidate_repo = CandidatePostRepository()
    review_repo = ReviewItemRepository()
    score_repo = ScoreCardRepository()

    candidate = await candidate_repo.create(
        session,
        source_url=f"https://example.com/{source_post_id}",
        source_time="day",
        source_post_id=source_post_id,
        author_handle="tester",
        raw_content=f"Raw content for {source_post_id}",
        captured_at=captured_at,
        dedup_fingerprint=f"fp-{source_post_id}",
    )
    await candidate_repo.transition_status(session, candidate, "scored")
    await candidate_repo.transition_status(session, candidate, "queued")
    await review_repo.create(
        session,
        candidate_post_id=candidate.id,
        english_draft=f"{source_post_id} draft.",
        chinese_translation_full="翻譯內容",
        risk_tags=["low"],
        threads_draft=f"Threads draft for {source_post_id}",
    )
    await score_repo.create(
        session,
        candidate_post_id=candidate.id,
        novelty_score=4.0,
        depth_score=4.0,
        tension_score=4.0,
        reflective_impact_score=4.0,
        engagement_score=4.0,
        risk_score=1,
        content_score=4.0,
        final_score=final_score,
        score_version="v1",
    )


@pytest.mark.asyncio
async def test_run_daily_summary_cycle_archives_stale_items_and_reports_archive_stats(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await _create_review_item(
            session,
            source_post_id="stale-high-score",
            captured_at=datetime.now(tz=UTC) - timedelta(days=20),
            final_score=4.8,
        )
        await _create_review_item(
            session,
            source_post_id="fresh-pending",
            captured_at=datetime.now(tz=UTC) - timedelta(days=2),
            final_score=4.1,
        )
        await session.commit()

    telegram_clients: list[_StubTelegramClient] = []

    def build_client(bot_token: str) -> _StubTelegramClient:
        client = _StubTelegramClient(bot_token)
        telegram_clients.append(client)
        return client

    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="bot-token",
            telegram_chat_id="12345",
        ),
    )
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(scheduler, "TelegramClient", build_client)

    await scheduler.run_daily_summary_cycle()

    async with session_factory() as session:
        archived_review = await ReviewItemRepository().list(session, status="archived", limit=10)
        pending_review = await ReviewItemRepository().list(session, status="pending", limit=10)

    assert len(telegram_clients) == 1
    assert telegram_clients[0].closed is True
    assert len(archived_review) == 1
    assert len(pending_review) == 1
    message = telegram_clients[0].sent_messages[0][1]
    assert "Auto-archived: 1" in message
    assert "Pending: 1" in message
    assert "https://example.com/stale-high-score" in message
