from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.app import create_app
from src.api.telegram_routes import build_telegram_webhook_secret
from src.api.telegram_routes import router as telegram_router
from src.models.base import Base, get_session
from src.models.candidate_post import CandidatePost, CandidatePostRepository
from src.models.review_item import ReviewItem, ReviewItemRepository
from src.models.score_card import ScoreCardRepository
from src.services.telegram_service import TelegramService


class _StubTelegramClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str, dict | None]] = []
        self.answered_callbacks: list[tuple[str, str | None]] = []

    async def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict:
        self.sent_messages.append((chat_id, text, reply_markup))
        return {"ok": True}

    async def edit_message_text(self, chat_id: str, message_id: int, text: str, reply_markup: dict | None = None) -> dict:
        _ = (chat_id, message_id, text, reply_markup)
        return {"ok": True}

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict:
        self.answered_callbacks.append((callback_query_id, text))
        return {"ok": True}


async def _build_app_with_telegram() -> tuple[object, async_sessionmaker, _StubTelegramClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app = create_app()
    app.include_router(telegram_router)

    async def override_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    telegram_client = _StubTelegramClient()
    app.state.settings = SimpleNamespace(
        telegram_bot_token="test-telegram-token",
        telegram_chat_id="12345",
        ingestion_time="hour",
        ingestion_sort="top",
        ingestion_limit=20,
    )
    app.state.telegram_client = telegram_client
    app.state.telegram_service = TelegramService(telegram_client, "12345")
    app.state.telegram_webhook_registered = True

    return app, async_session, telegram_client


async def _create_archived_item(
    session,
    *,
    source_post_id: str,
    final_score: float,
    reviewed_by: str,
) -> tuple[str, str]:
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
        captured_at=datetime.now(tz=UTC) - timedelta(days=20),
        dedup_fingerprint=f"fp-{source_post_id}",
    )
    await candidate_repo.transition_status(session, candidate, "scored")
    await candidate_repo.transition_status(session, candidate, "queued")
    review_item = await review_repo.create(
        session,
        candidate_post_id=candidate.id,
        english_draft=f"{source_post_id} title. More detail.",
        chinese_translation_full="翻譯內容",
        risk_tags=["low"],
        threads_draft=f"Threads {source_post_id}",
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
    await review_repo.decide(
        session,
        review_item_id=review_item.id,
        decision="archived",
        reviewed_by=reviewed_by,
    )
    await session.commit()
    return candidate.id, review_item.id


def _webhook_headers() -> dict[str, str]:
    return {
        "X-Telegram-Bot-Api-Secret-Token": build_telegram_webhook_secret("test-telegram-token"),
    }


@pytest.mark.asyncio
async def test_recall_command_returns_empty_state_when_no_items_exist() -> None:
    app, _, telegram_client = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/recall"}},
        )

    assert response.status_code == 200
    assert telegram_client.sent_messages == [("12345", "No recallable items.", None)]


@pytest.mark.asyncio
async def test_recall_command_lists_only_eligible_items() -> None:
    app, async_session, telegram_client = await _build_app_with_telegram()

    async with async_session() as session:
        _, first_review_id = await _create_archived_item(
            session,
            source_post_id="eligible-one",
            final_score=4.9,
            reviewed_by="archive-worker",
        )
        _, second_review_id = await _create_archived_item(
            session,
            source_post_id="eligible-two",
            final_score=4.4,
            reviewed_by="archive-worker",
        )
        await _create_archived_item(
            session,
            source_post_id="manual-item",
            final_score=4.8,
            reviewed_by="telegram",
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/recall"}},
        )

    assert response.status_code == 200
    assert len(telegram_client.sent_messages) == 1
    recall_text = telegram_client.sent_messages[0][1]
    recall_keyboard = telegram_client.sent_messages[0][2]
    assert "<b>Recallable items</b>" in recall_text
    assert "eligible-one title." in recall_text
    assert "eligible-two title." in recall_text
    assert "manual-item" not in recall_text
    assert recall_keyboard is not None
    assert recall_keyboard["inline_keyboard"][0][0]["callback_data"] == f"recall:{first_review_id}"
    assert recall_keyboard["inline_keyboard"][1][0]["callback_data"] == f"recall:{second_review_id}"


@pytest.mark.asyncio
async def test_recall_callback_transitions_item_back_to_queue() -> None:
    app, async_session, telegram_client = await _build_app_with_telegram()

    async with async_session() as session:
        candidate_id, review_item_id = await _create_archived_item(
            session,
            source_post_id="recallable",
            final_score=4.9,
            reviewed_by="archive-worker",
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "cb-1",
                    "data": f"recall:{review_item_id}",
                    "message": {"message_id": 9, "chat": {"id": 12345}, "text": "Recall item"},
                }
            },
        )

    async with async_session() as session:
        persisted_review = await session.scalar(select(ReviewItem).where(ReviewItem.id == review_item_id))
        persisted_candidate = await session.scalar(select(CandidatePost).where(CandidatePost.id == candidate_id))

    assert response.status_code == 200
    assert telegram_client.answered_callbacks == [("cb-1", "Item recalled.")]
    assert persisted_review is not None and persisted_review.decision == "pending"
    assert persisted_review.reviewed_by is None
    assert persisted_review.reviewed_at is None
    assert persisted_candidate is not None and persisted_candidate.status == "queued"


@pytest.mark.asyncio
async def test_recall_callback_handles_already_recalled_and_not_eligible() -> None:
    app, async_session, telegram_client = await _build_app_with_telegram()

    async with async_session() as session:
        _, recallable_review_id = await _create_archived_item(
            session,
            source_post_id="recall-once",
            final_score=4.7,
            reviewed_by="archive-worker",
        )
        _, manual_review_id = await _create_archived_item(
            session,
            source_post_id="manual-archive",
            final_score=4.8,
            reviewed_by="telegram",
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "cb-1",
                    "data": f"recall:{recallable_review_id}",
                    "message": {"message_id": 9, "chat": {"id": 12345}, "text": "Recall item"},
                }
            },
        )
        second_response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "cb-2",
                    "data": f"recall:{recallable_review_id}",
                    "message": {"message_id": 9, "chat": {"id": 12345}, "text": "Recall item"},
                }
            },
        )
        third_response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "cb-3",
                    "data": f"recall:{manual_review_id}",
                    "message": {"message_id": 9, "chat": {"id": 12345}, "text": "Recall item"},
                }
            },
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 200
    assert telegram_client.answered_callbacks == [
        ("cb-1", "Item recalled."),
        ("cb-2", "Item already recalled."),
        ("cb-3", "This item cannot be recalled."),
    ]
