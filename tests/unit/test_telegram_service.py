import pytest

from src.services.telegram_service import (
    CONTENT_TRUNCATION_SUFFIX,
    MAX_TELEGRAM_MESSAGE_LENGTH,
    TelegramService,
)


class _StubTelegramClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str, dict | None]] = []
        self.edited_messages: list[tuple[str, int, str, dict | None]] = []

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


def _review_item(**overrides) -> dict:
    item = {
        "id": "review-1",
        "threadsDraft": "Threads draft",
        "translatedContent": "Translated content",
        "draftContent": "English draft",
        "topCommentsSnapshot": [{"author_handle": "alice", "content_text": "Original comment", "upvotes": 3}],
        "topCommentsTranslated": [{"author_handle": "alice", "content_text": "Translated comment", "upvotes": 3}],
        "aiScore": {"finalScore": 8.7},
        "riskTags": ["low", "news"],
        "sourceUrl": "https://example.com/post/1",
        "followUpRationale": "Follow-up rationale",
    }
    item.update(overrides)
    return item


def test_format_review_message_uses_threads_draft_and_metadata() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    message = service.format_review_message(_review_item())

    assert "<b>Review item</b> <code>review-1</code>" in message
    assert "Threads draft" in message
    assert "<b>Final score:</b> 8.7" in message
    assert "<b>Risk tags:</b> low, news" in message
    assert 'href="https://example.com/post/1"' in message


def test_format_review_message_falls_back_when_threads_draft_missing() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    message = service.format_review_message(_review_item(threadsDraft="", translatedContent="Use this"))

    assert "Use this" in message


def test_format_review_message_truncates_content_and_enforces_limit() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")
    long_text = "A" * 5000

    message = service.format_review_message(_review_item(threadsDraft=long_text))

    assert CONTENT_TRUNCATION_SUFFIX in message
    assert len(message) <= MAX_TELEGRAM_MESSAGE_LENGTH


def test_build_review_inline_keyboard_uses_action_id_callback_data() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    keyboard = service.build_review_inline_keyboard("abc-123")

    assert keyboard == {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": "approve:abc-123"},
                {"text": "Reject", "callback_data": "reject:abc-123"},
            ],
            [
                {"text": "Reject+Comment", "callback_data": "comment:abc-123"},
                {"text": "Edit Draft", "callback_data": "edit:abc-123"},
            ],
        ]
    }


def test_build_recall_inline_keyboard_uses_recall_callback_data() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    keyboard = service.build_recall_inline_keyboard("abc-123")

    assert keyboard == {"inline_keyboard": [[{"text": "Recall", "callback_data": "recall:abc-123"}]]}


@pytest.mark.asyncio
async def test_push_pending_items_sends_one_message_per_item() -> None:
    telegram_client = _StubTelegramClient()
    service = TelegramService(telegram_client, "chat-1")

    await service.push_pending_items([_review_item(id="one"), _review_item(id="two")])

    assert len(telegram_client.sent_messages) == 2
    assert telegram_client.sent_messages[0][0] == "chat-1"
    assert telegram_client.sent_messages[0][2]["inline_keyboard"][0][0]["callback_data"] == "approve:one"


def test_format_ingestion_digest_includes_threshold_bands_and_pending_count() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    message = service.format_ingestion_digest(
        fetched_count=12,
        persisted_count=8,
        filtered_duplicate_count=4,
        archived_count=3,
        score_breakdown={"auto_publish": 2, "review_queue": 3, "archived": 3},
        risk_breakdown={"low": 5, "medium": 2, "high": 1},
        auto_publish_count=2,
        auto_publish_label="would qualify",
        pending_total=11,
        review_min_score=3.5,
        auto_publish_min_score=4.0,
    )

    assert "Ingestion summary" in message
    assert "⭐ &gt;= 4.0: 2 posts" in message
    assert "✅ &gt;= 3.5: 3 posts (queued)" in message
    assert "📦 &lt; 3.5: 3 posts (archived)" in message
    assert "Risk: Low 5 | Medium 2 | High 1" in message
    assert "Auto-publish: 2 would qualify" in message
    assert "Pending review: 11 total" in message
    assert message.endswith("/pending to review")


@pytest.mark.asyncio
async def test_update_message_with_decision_appends_decision_and_removes_keyboard() -> None:
    telegram_client = _StubTelegramClient()
    service = TelegramService(telegram_client, "chat-1")

    await service.update_message_with_decision(
        "chat-1",
        123,
        "<b>Original</b>",
        "approved",
        "2026-03-07T12:00:00+00:00",
        comment="looks good",
    )

    assert telegram_client.edited_messages == [
        (
            "chat-1",
            123,
            "<b>Original</b>\n\n<b>Decision:</b> approved\n<b>At:</b> 2026-03-07T12:00:00+00:00\n<b>Comment:</b> looks good",
            None,
        )
    ]


def test_state_management_clears_overlapping_interactions() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    service.set_pending_comment(42, "item-a")
    assert service.get_pending_comment(42) == "item-a"

    service.set_pending_edit(42, "item-b")
    assert service.get_pending_comment(42) is None
    assert service.get_pending_edit(42) == "item-b"

    assert service.clear_pending_state(42) is True
    assert service.get_pending_edit(42) is None
    assert service.clear_pending_state(42) is False


def test_format_pending_list_limits_to_ten_items() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")
    items = [
        _review_item(id=str(index), threadsDraft=f"Draft {index}. Second sentence that should not appear.")
        for index in range(12)
    ]

    message = service.format_pending_list(items)

    assert "1. Draft 0. | score 8.7 | risk low, news" in message
    assert "10. Draft 9. | score 8.7 | risk low, news" in message
    assert "Draft 10" not in message
    assert "… and 2 more" in message
    assert "Use /review &lt;number&gt; to open full details." in message


def test_build_review_detail_messages_orders_sections_with_threads_last() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    messages = service.build_review_detail_messages(
        _review_item(
            draftContent="Full original draft",
            translatedContent="Full translated draft",
            threadsDraft="Threads draft final",
        )
    )

    rendered = [message["text"] for message in messages]

    assert rendered[0].startswith("<b>Review item</b>")
    assert "<b>Original draft</b>" in rendered[1]
    assert "<b>Translated draft</b>" in rendered[2]
    assert "<b>Comments (original)</b>" in rendered[3]
    assert "<b>Comments (translated)</b>" in rendered[4]
    assert "<b>Threads draft</b>" in rendered[5]
    assert "Threads draft final" in rendered[5]
    assert messages[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "approve:review-1"


def test_format_stats_health_help_and_recall_messages() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    stats_message = service.format_stats_message(
        {
            "pendingCount": 5,
            "approvedTodayCount": 2,
            "rejectedTodayCount": 1,
            "publishedTodayCount": 3,
            "archivedCount": 4,
            "ingestedTodayCount": 8,
            "failedJobCount": 1,
            "highScoreRecalls": [{"sourceUrl": "https://example.com/post/9", "finalScore": 4.8}],
            "topPendingItems": [_review_item(threadsDraft="One"), _review_item(threadsDraft="Two")],
        }
    )
    health_message = service.format_health_message(
        {
            "status": "degraded",
            "database": True,
            "webhook": True,
            "errors": ["database timeout"],
        }
    )
    help_message = service.format_help_message()
    recall_message = service.format_recall_list(
        [
            {
                "reviewItemId": "review-9",
                "title": "Archived title. Extra sentence.",
                "sourceUrl": "https://example.com/post/9",
                "finalScore": 4.8,
            }
        ]
    )

    assert "Pending: 5" in stats_message
    assert "Auto-archived: 4" in stats_message
    assert "Failed jobs today: 1" in stats_message
    assert "https://example.com/post/9" in stats_message
    assert "- One (8.7)" in stats_message
    assert "Status: degraded" in health_message
    assert "Database: ok" in health_message
    assert "Webhook: ok" in health_message
    assert "Queue:" not in health_message
    assert "/review &lt;number&gt; - Show full details for one pending item" in help_message
    assert "/ingest [time] [sort] [limit] - Start ingestion; tokens can be in any order" in help_message
    assert "/regenerate [number] - Regenerate empty translations or Threads drafts" in help_message
    assert "/recall - Show high-score archived items you can recall" in help_message
    assert "/cancel - Cancel the current comment or edit flow" in help_message
    assert "<b>Recallable items</b>" in recall_message
    assert "1. Archived title." in recall_message
    assert "Score: 4.8" in recall_message


def test_format_recall_list_returns_empty_state_message() -> None:
    service = TelegramService(_StubTelegramClient(), "chat-1")

    assert service.format_recall_list([]) == "No recallable items."
