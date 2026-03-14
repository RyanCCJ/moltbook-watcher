from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.app import create_app
from src.api.telegram_routes import build_telegram_webhook_secret
from src.api.telegram_routes import router as telegram_router
from src.models.base import Base, get_session
from src.models.candidate_post import CandidatePostRepository
from src.models.review_item import ReviewItem, ReviewItemRepository
from src.models.score_card import ScoreCardRepository
from src.services.telegram_service import TelegramService


class _StubTelegramClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str, dict | None]] = []
        self.edited_messages: list[tuple[str, int, str, dict | None]] = []
        self.answered_callbacks: list[tuple[str, str | None]] = []

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        self.sent_messages.append((chat_id, text, reply_markup))
        return {"ok": True}

    async def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        self.edited_messages.append((chat_id, message_id, text, reply_markup))
        return {"ok": True}

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict:
        self.answered_callbacks.append((callback_query_id, text))
        return {"ok": True}


async def _build_app_with_telegram() -> tuple[object, async_sessionmaker, _StubTelegramClient, str]:
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

    candidate_repo = CandidatePostRepository()
    review_repo = ReviewItemRepository()
    score_repo = ScoreCardRepository()

    async with async_session() as session:
        candidate = await candidate_repo.create(
            session,
            source_url="https://moltbook.com/p/telegram-review",
            source_time="day",
            source_post_id="telegram-review",
            author_handle="reviewer",
            raw_content="Telegram raw content",
            captured_at=datetime.now(tz=UTC),
            dedup_fingerprint="telegram-hash",
        )
        await candidate_repo.transition_status(session, candidate, target_status="scored")
        await candidate_repo.transition_status(session, candidate, target_status="queued")
        review_item = await review_repo.create(
            session,
            candidate_post_id=candidate.id,
            english_draft="English draft. Extra detail that should stay out of /pending.",
            chinese_translation_full="Translated draft full text",
            risk_tags=["low"],
            threads_draft="Threads draft. Extra detail that should stay out of /pending.",
            top_comments_snapshot=[{"author_handle": "alice", "content_text": "Original comment", "upvotes": 3}],
            top_comments_translated=[{"author_handle": "alice", "content_text": "Translated comment", "upvotes": 3}],
            follow_up_rationale="Follow-up rationale",
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
            final_score=4.5,
            score_version="v1",
        )
        await session.commit()

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

    return app, async_session, telegram_client, review_item.id


def _webhook_headers() -> dict[str, str]:
    return {
        "X-Telegram-Bot-Api-Secret-Token": build_telegram_webhook_secret("test-telegram-token"),
    }


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_invalid_secret() -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/telegram/webhook", json={"message": {"chat": {"id": 12345}}})

    assert response.status_code == 403
    assert telegram_client.sent_messages == []


@pytest.mark.asyncio
async def test_telegram_webhook_ignores_unauthorized_chat() -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 99999}, "text": "/help"}},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert telegram_client.sent_messages == []


@pytest.mark.asyncio
async def test_telegram_approve_callback_updates_review_and_message() -> None:
    app, async_session, telegram_client, review_item_id = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "cb-1",
                    "data": f"approve:{review_item_id}",
                    "message": {
                        "message_id": 77,
                        "text": "<b>Original</b>",
                        "chat": {"id": 12345},
                    },
                }
            },
        )

    assert response.status_code == 200
    assert telegram_client.answered_callbacks == [("cb-1", "Approved")]
    assert telegram_client.edited_messages[0][0] == "12345"
    assert "<b>Decision:</b> approved" in telegram_client.edited_messages[0][2]

    async with async_session() as session:
        persisted = await session.scalar(select(ReviewItem).where(ReviewItem.id == review_item_id))

    assert persisted is not None
    assert persisted.decision == "approved"
    assert persisted.reviewed_by == "telegram"


@pytest.mark.asyncio
async def test_telegram_reject_comment_flow_tracks_state_and_rejects() -> None:
    app, async_session, telegram_client, review_item_id = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        callback_response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "cb-2",
                    "data": f"reject:{review_item_id}",
                    "message": {
                        "message_id": 78,
                        "text": "<b>Original</b>",
                        "chat": {"id": 12345},
                    },
                }
            },
        )
        message_response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "message": {
                    "message_id": 79,
                    "chat": {"id": 12345},
                    "text": "Needs more detail",
                }
            },
        )

    assert callback_response.status_code == 200
    assert message_response.status_code == 200
    assert telegram_client.sent_messages[0][1] == "Please type your rejection comment:"
    assert telegram_client.sent_messages[-1][1] == "Rejected with comment."
    assert "Needs more detail" in telegram_client.edited_messages[0][2]
    assert app.state.telegram_service.get_pending_comment(12345) is None

    async with async_session() as session:
        persisted = await session.scalar(select(ReviewItem).where(ReviewItem.id == review_item_id))

    assert persisted is not None
    assert persisted.decision == "rejected"


@pytest.mark.asyncio
async def test_telegram_edit_flow_updates_threads_draft() -> None:
    app, async_session, telegram_client, review_item_id = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "cb-3",
                    "data": f"edit:{review_item_id}",
                    "message": {"message_id": 80, "text": "<b>Original</b>", "chat": {"id": 12345}},
                }
            },
        )
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"message_id": 81, "chat": {"id": 12345}, "text": "Updated draft"}},
        )

    assert response.status_code == 200
    assert telegram_client.sent_messages[0][1] == "Send me the new draft text:"
    assert telegram_client.sent_messages[-1][1] == "Draft updated."

    async with async_session() as session:
        persisted = await session.scalar(select(ReviewItem).where(ReviewItem.id == review_item_id))

    assert persisted is not None
    assert persisted.threads_draft == "Updated draft"


@pytest.mark.asyncio
async def test_telegram_pending_help_cancel_and_unknown_commands() -> None:
    app, _, telegram_client, review_item_id = await _build_app_with_telegram()
    app.state.telegram_service.set_pending_comment(12345, review_item_id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/pending"}},
        )
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/help"}},
        )
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/cancel"}},
        )
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "???"}},
        )

    assert response.status_code == 200
    assert "Pending review items" in telegram_client.sent_messages[0][1]
    assert "Threads draft." in telegram_client.sent_messages[0][1]
    assert "Use /review &lt;number&gt; to open full details." in telegram_client.sent_messages[0][1]
    assert "Available commands" in telegram_client.sent_messages[1][1]
    assert "/ingest [time] [sort] [limit]" in telegram_client.sent_messages[1][1]
    assert telegram_client.sent_messages[2][1] == "Cancelled."
    assert telegram_client.sent_messages[3][1] == "Unknown command. Use /help to see available commands."


@pytest.mark.asyncio
async def test_telegram_review_command_returns_full_details_with_threads_last() -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/review 1"}},
        )

    assert response.status_code == 200
    assert len(telegram_client.sent_messages) == 6
    assert "<b>Original draft</b>" in telegram_client.sent_messages[1][1]
    assert "<b>Translated draft</b>" in telegram_client.sent_messages[2][1]
    assert "<b>Comments (original)</b>" in telegram_client.sent_messages[3][1]
    assert "<b>Comments (translated)</b>" in telegram_client.sent_messages[4][1]
    assert "<b>Threads draft</b>" in telegram_client.sent_messages[5][1]
    assert telegram_client.sent_messages[5][2]["inline_keyboard"][0][0]["callback_data"].startswith("approve:")


@pytest.mark.asyncio
async def test_telegram_review_command_rejects_missing_or_invalid_index() -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        bad_usage = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/review"}},
        )
        missing_item = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/review 9"}},
        )

    assert bad_usage.status_code == 200
    assert missing_item.status_code == 200
    assert telegram_client.sent_messages[0][1] == "Usage: /review &lt;number&gt;"
    assert telegram_client.sent_messages[1][1] == "Review item number not found in the current pending list."


@pytest.mark.asyncio
async def test_telegram_ingest_publish_stats_and_health_commands(monkeypatch) -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()

    async def fake_ingestion(*, time: str = "hour", sort: str = "top", limit: int = 20) -> dict[str, int | str]:
        assert (time, sort, limit) == ("hour", "top", 20)
        return {
            "time": time,
            "sort": sort,
            "limit": limit,
            "fetched_count": 2,
            "persisted_count": 2,
            "filtered_duplicate_count": 0,
            "review_items_created": 1,
        }

    async def fake_publish() -> dict[str, int]:
        return {
            "scheduled_count": 1,
            "published_count": 1,
            "retry_scheduled_count": 0,
            "failed_terminal_count": 0,
        }

    created_coroutines: list = []

    async def run_created_coroutines() -> None:
        for coroutine in created_coroutines:
            await coroutine

    monkeypatch.setattr("src.api.telegram_routes.run_ingestion_once", fake_ingestion)
    monkeypatch.setattr("src.api.telegram_routes.run_publish_once", fake_publish)
    monkeypatch.setattr("src.api.telegram_routes._schedule_background_task", lambda coro: created_coroutines.append(coro))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/ingest"}},
        )
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/publish"}},
        )
        await run_created_coroutines()
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/stats"}},
        )
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/health"}},
        )

    assert response.status_code == 200
    assert "Ingestion started…" in telegram_client.sent_messages[0][1]
    assert "Time: hour" in telegram_client.sent_messages[0][1]
    assert "Limit: 20" in telegram_client.sent_messages[0][1]
    assert telegram_client.sent_messages[1][1] == "Publish cycle started…"
    assert "Publish finished." in telegram_client.sent_messages[2][1]
    assert "Pipeline stats" in telegram_client.sent_messages[3][1]
    assert "System health" in telegram_client.sent_messages[4][1]


@pytest.mark.asyncio
async def test_telegram_ingest_command_accepts_tokens_in_any_order(monkeypatch) -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()
    created_coroutines: list = []

    async def fake_ingestion(*, time: str = "hour", sort: str = "top", limit: int = 20) -> dict[str, int | str]:
        assert (time, sort, limit) == ("week", "rising", 12)
        return {
            "time": time,
            "sort": sort,
            "limit": limit,
            "fetched_count": 1,
            "persisted_count": 1,
            "filtered_duplicate_count": 0,
            "review_items_created": 1,
        }

    monkeypatch.setattr("src.api.telegram_routes.run_ingestion_once", fake_ingestion)
    monkeypatch.setattr("src.api.telegram_routes._schedule_background_task", lambda coro: created_coroutines.append(coro))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/ingest 12 week rising"}},
        )

    for coroutine in created_coroutines:
        await coroutine

    assert response.status_code == 200
    assert "Time: week" in telegram_client.sent_messages[0][1]
    assert "Sort: rising" in telegram_client.sent_messages[0][1]
    assert "Limit: 12" in telegram_client.sent_messages[0][1]


@pytest.mark.asyncio
async def test_telegram_ingest_command_rejects_duplicate_or_unknown_tokens(monkeypatch) -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()
    created_coroutines: list = []

    monkeypatch.setattr("src.api.telegram_routes._schedule_background_task", lambda coro: created_coroutines.append(coro))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        duplicate = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/ingest day week"}},
        )
        unknown = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/ingest nonsense"}},
        )

    assert duplicate.status_code == 200
    assert unknown.status_code == 200
    assert "Time can only be set once." in telegram_client.sent_messages[0][1]
    assert "Supported time: hour/day/week/month/all." in telegram_client.sent_messages[1][1]
    assert created_coroutines == []
