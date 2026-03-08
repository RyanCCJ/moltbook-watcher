from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings, get_settings
from src.integrations.telegram_client import TelegramClient
from src.models.base import check_db_health, get_session
from src.models.lifecycle import ReviewDecision
from src.models.review_item import ReviewItemRepository
from src.services.logging_service import get_logger
from src.services.telegram_reporting import build_stats_payload, load_review_item_payloads
from src.services.telegram_service import TelegramService
from src.workers.archive_worker import ArchiveWorker
from src.workers.runtime import run_ingestion_once, run_publish_once

logger = get_logger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])
_INGEST_TIME_OPTIONS = {"hour", "day", "week", "month", "all"}
_INGEST_SORT_OPTIONS = {"hot", "new", "top", "rising"}


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    settings = _get_app_settings(request)
    expected_secret = build_telegram_webhook_secret(settings.telegram_bot_token)
    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        update = await request.json()
    except Exception as error:
        logger.error("telegram_update_parse_failed", error=str(error))
        return {"ok": True}

    try:
        chat_id = _extract_chat_id(update)
        if chat_id is None or str(chat_id) != settings.telegram_chat_id:
            return {"ok": True}

        telegram_service = request.app.state.telegram_service
        telegram_client = request.app.state.telegram_client

        if "callback_query" in update:
            await _handle_callback_query(
                update["callback_query"],
                session=session,
                telegram_service=telegram_service,
                telegram_client=telegram_client,
            )
        elif "message" in update:
            await _handle_message(
                request=request,
                message=update["message"],
                session=session,
                telegram_service=telegram_service,
                telegram_client=telegram_client,
            )
    except Exception as error:
        logger.error("telegram_update_handling_failed", error=str(error))

    return {"ok": True}


def build_telegram_webhook_secret(bot_token: str) -> str:
    return hashlib.sha256(bot_token.encode("utf-8")).hexdigest()[:32]


async def _handle_callback_query(
    callback_query: dict[str, Any],
    *,
    session: AsyncSession,
    telegram_service: TelegramService,
    telegram_client: TelegramClient,
) -> None:
    callback_query_id = str(callback_query["id"])
    message = callback_query.get("message") or {}
    chat_id = str(message.get("chat", {}).get("id", ""))
    message_id = int(message.get("message_id", 0))
    original_text = str(message.get("text") or "")
    review_repo = ReviewItemRepository()

    action, review_item_id = _parse_callback_data(str(callback_query.get("data") or ""))
    if action == "approve":
        await _apply_decision(
            session=session,
            review_repo=review_repo,
            review_item_id=review_item_id,
            decision=ReviewDecision.APPROVED.value,
            chat_id=chat_id,
            message_id=message_id,
            original_text=original_text,
            telegram_service=telegram_service,
            telegram_client=telegram_client,
            callback_query_id=callback_query_id,
            success_text="Approved",
        )
        return
    if action == "reject":
        await _apply_decision(
            session=session,
            review_repo=review_repo,
            review_item_id=review_item_id,
            decision=ReviewDecision.REJECTED.value,
            chat_id=chat_id,
            message_id=message_id,
            original_text=original_text,
            telegram_service=telegram_service,
            telegram_client=telegram_client,
            callback_query_id=callback_query_id,
            success_text="Rejected",
        )
        return
    if action == "comment":
        telegram_service.set_pending_comment(
            int(chat_id),
            review_item_id,
            message_id=message_id,
            original_text=original_text,
        )
        await telegram_client.send_message(chat_id, "Please type your rejection comment:")
        await telegram_client.answer_callback_query(callback_query_id, text="Send comment")
        return
    if action == "edit":
        telegram_service.set_pending_edit(int(chat_id), review_item_id)
        await telegram_client.send_message(chat_id, "Send me the new draft text:")
        await telegram_client.answer_callback_query(callback_query_id, text="Send updated draft")
        return
    if action == "recall":
        outcome = await ArchiveWorker().recall_item(session, review_item_id)
        if outcome == "recalled":
            await session.commit()
            await telegram_client.answer_callback_query(callback_query_id, text="Item recalled.")
            return
        if outcome == "already_recalled":
            await telegram_client.answer_callback_query(callback_query_id, text="Item already recalled.")
            return
        await telegram_client.answer_callback_query(callback_query_id, text="This item cannot be recalled.")
        return

    await telegram_client.answer_callback_query(callback_query_id, text="Unknown action")


async def _apply_decision(
    *,
    session: AsyncSession,
    review_repo: ReviewItemRepository,
    review_item_id: str,
    decision: str,
    chat_id: str,
    message_id: int,
    original_text: str,
    telegram_service: TelegramService,
    telegram_client: TelegramClient,
    callback_query_id: str,
    success_text: str,
) -> None:
    try:
        review_item = await review_repo.decide(
            session,
            review_item_id=review_item_id,
            decision=decision,
            reviewed_by="telegram",
        )
        await session.commit()
    except ValueError as error:
        message = str(error)
        if message == "Decision already submitted":
            await telegram_client.answer_callback_query(callback_query_id, text="Item already decided")
            return
        await telegram_client.answer_callback_query(callback_query_id, text=message)
        return

    await telegram_service.update_message_with_decision(
        chat_id,
        message_id,
        original_text,
        decision,
        review_item.reviewed_at or datetime.now(tz=UTC),
    )
    await telegram_client.answer_callback_query(callback_query_id, text=success_text)


async def _handle_message(
    *,
    request: Request,
    message: dict[str, Any],
    session: AsyncSession,
    telegram_service: TelegramService,
    telegram_client: TelegramClient,
) -> None:
    chat_id = int(message.get("chat", {}).get("id", 0))
    text = str(message.get("text") or "").strip()
    if not text:
        return

    if text == "/cancel":
        await _handle_cancel(chat_id=chat_id, telegram_client=telegram_client, telegram_service=telegram_service)
        return

    if telegram_service.get_pending_comment(chat_id) and not text.startswith("/"):
        await _handle_pending_comment(
            chat_id=chat_id,
            comment=text,
            session=session,
            telegram_service=telegram_service,
            telegram_client=telegram_client,
        )
        return

    if telegram_service.get_pending_edit(chat_id) and not text.startswith("/"):
        await _handle_pending_edit(
            chat_id=chat_id,
            new_draft=text,
            session=session,
            telegram_service=telegram_service,
            telegram_client=telegram_client,
        )
        return

    if text.startswith("/"):
        await _handle_command(
            request=request,
            chat_id=chat_id,
            command_text=text,
            session=session,
            telegram_service=telegram_service,
            telegram_client=telegram_client,
        )
        return

    await telegram_client.send_message(str(chat_id), "Unknown command. Use /help to see available commands.")


async def _handle_pending_comment(
    *,
    chat_id: int,
    comment: str,
    session: AsyncSession,
    telegram_service: TelegramService,
    telegram_client: TelegramClient,
) -> None:
    review_item_id = telegram_service.get_pending_comment(chat_id)
    if review_item_id is None:
        return

    review_repo = ReviewItemRepository()
    try:
        review_item = await review_repo.decide(
            session,
            review_item_id=review_item_id,
            decision=ReviewDecision.REJECTED.value,
            reviewed_by="telegram",
        )
        await session.commit()
    except ValueError as error:
        telegram_service.clear_pending_comment(chat_id)
        await telegram_client.send_message(str(chat_id), str(error))
        return

    context = telegram_service.get_pending_comment_context(chat_id)
    telegram_service.clear_pending_comment(chat_id)
    if context is not None:
        message_id, original_text = context
        await telegram_service.update_message_with_decision(
            str(chat_id),
            message_id,
            original_text,
            ReviewDecision.REJECTED.value,
            review_item.reviewed_at or datetime.now(tz=UTC),
            comment=comment,
        )
    await telegram_client.send_message(str(chat_id), "Rejected with comment.")


async def _handle_pending_edit(
    *,
    chat_id: int,
    new_draft: str,
    session: AsyncSession,
    telegram_service: TelegramService,
    telegram_client: TelegramClient,
) -> None:
    review_item_id = telegram_service.get_pending_edit(chat_id)
    if review_item_id is None:
        return

    review_repo = ReviewItemRepository()
    try:
        await review_repo.update_draft(session, review_item_id=review_item_id, threads_draft=new_draft)
        await session.commit()
    except ValueError as error:
        telegram_service.clear_pending_edit(chat_id)
        await telegram_client.send_message(str(chat_id), str(error))
        return

    telegram_service.clear_pending_edit(chat_id)
    await telegram_client.send_message(str(chat_id), "Draft updated.")


async def _handle_command(
    *,
    request: Request,
    chat_id: int,
    command_text: str,
    session: AsyncSession,
    telegram_service: TelegramService,
    telegram_client: TelegramClient,
) -> None:
    settings = _get_app_settings(request)
    parts = command_text.split()
    command = parts[0]
    arguments = parts[1:]
    argument = " ".join(arguments)

    if command == "/pending":
        items = await load_review_item_payloads(session, status=ReviewDecision.PENDING.value, limit=10)
        await telegram_client.send_message(str(chat_id), telegram_service.format_pending_list(items))
        return

    if command == "/review":
        if not argument.isdigit():
            await telegram_client.send_message(str(chat_id), "Usage: /review &lt;number&gt;")
            return
        items = await load_review_item_payloads(session, status=ReviewDecision.PENDING.value, limit=10)
        index = int(argument)
        if index < 1 or index > len(items):
            await telegram_client.send_message(str(chat_id), "Review item number not found in the current pending list.")
            return
        for message in telegram_service.build_review_detail_messages(items[index - 1]):
            await telegram_client.send_message(
                str(chat_id),
                message["text"],
                reply_markup=message["reply_markup"],
            )
        return

    if command == "/ingest":
        try:
            ingest_options = _parse_ingest_arguments(arguments, settings=settings)
        except ValueError as error:
            await telegram_client.send_message(str(chat_id), str(error))
            return
        await telegram_client.send_message(
            str(chat_id),
            (
                "Ingestion started…\n"
                f"Time: {ingest_options['time']}\n"
                f"Sort: {ingest_options['sort']}\n"
                f"Limit: {ingest_options['limit']}"
            ),
        )
        _schedule_background_task(
            _run_ingestion_follow_up(
                str(chat_id),
                telegram_client,
                time=str(ingest_options["time"]),
                sort=str(ingest_options["sort"]),
                limit=int(ingest_options["limit"]),
            )
        )
        return

    if command == "/publish":
        await telegram_client.send_message(str(chat_id), "Publish cycle started…")
        _schedule_background_task(_run_publish_follow_up(str(chat_id), telegram_client))
        return

    if command == "/stats":
        stats = await build_stats_payload(session)
        await telegram_client.send_message(str(chat_id), telegram_service.format_stats_message(stats))
        return

    if command == "/recall":
        recall_items = await ArchiveWorker().build_high_score_recall(session, min_score=4.0)
        if not recall_items:
            await telegram_client.send_message(str(chat_id), telegram_service.format_recall_list(recall_items))
            return
        recall_keyboard = {
            "inline_keyboard": [
                telegram_service.build_recall_inline_keyboard(str(item["reviewItemId"]))["inline_keyboard"][0]
                for item in recall_items
            ]
        }
        await telegram_client.send_message(
            str(chat_id),
            telegram_service.format_recall_list(recall_items),
            reply_markup=recall_keyboard,
        )
        return

    if command == "/health":
        db_ok = await check_db_health(session)
        health_data = {
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "webhook": bool(getattr(request.app.state, "telegram_webhook_registered", False)),
        }
        await telegram_client.send_message(str(chat_id), telegram_service.format_health_message(health_data))
        return

    if command == "/help":
        await telegram_client.send_message(str(chat_id), telegram_service.format_help_message())
        return

    if command == "/cancel":
        await _handle_cancel(chat_id=chat_id, telegram_client=telegram_client, telegram_service=telegram_service)
        return

    await telegram_client.send_message(str(chat_id), "Unknown command. Use /help to see available commands.")


async def _handle_cancel(
    *,
    chat_id: int,
    telegram_client: TelegramClient,
    telegram_service: TelegramService,
) -> None:
    cleared = telegram_service.clear_pending_state(chat_id)
    message = "Cancelled." if cleared else "Nothing to cancel."
    await telegram_client.send_message(str(chat_id), message)


def _parse_ingest_arguments(arguments: list[str], *, settings: Settings) -> dict[str, str | int]:
    time = settings.ingestion_time
    sort = settings.ingestion_sort
    limit = settings.ingestion_limit
    seen_time = False
    seen_sort = False
    seen_limit = False

    for token in arguments:
        normalized = token.strip().lower()
        if not normalized:
            continue
        if normalized in _INGEST_TIME_OPTIONS:
            if seen_time:
                raise ValueError("Usage: /ingest [time] [sort] [limit]. Time can only be set once.")
            time = normalized
            seen_time = True
            continue
        if normalized in _INGEST_SORT_OPTIONS:
            if seen_sort:
                raise ValueError("Usage: /ingest [time] [sort] [limit]. Sort can only be set once.")
            sort = normalized
            seen_sort = True
            continue
        if normalized.isdigit():
            if seen_limit:
                raise ValueError("Usage: /ingest [time] [sort] [limit]. Limit can only be set once.")
            limit_value = int(normalized)
            if limit_value < 1:
                raise ValueError("Usage: /ingest [time] [sort] [limit]. Limit must be a positive integer.")
            limit = limit_value
            seen_limit = True
            continue
        raise ValueError(
            "Usage: /ingest [time] [sort] [limit]. "
            "Supported time: hour/day/week/month/all. Supported sort: hot/new/top/rising."
        )

    return {"time": time, "sort": sort, "limit": limit}


async def _run_ingestion_follow_up(
    chat_id: str,
    telegram_client: TelegramClient,
    *,
    time: str,
    sort: str,
    limit: int,
) -> None:
    try:
        await run_ingestion_once(time=time, sort=sort, limit=limit)
    except Exception as error:
        await telegram_client.send_message(chat_id, f"Ingestion failed: {error}")


async def _run_publish_follow_up(chat_id: str, telegram_client: TelegramClient) -> None:
    try:
        metrics = await run_publish_once()
    except Exception as error:
        await telegram_client.send_message(chat_id, f"Publish failed: {error}")
        return
    await telegram_client.send_message(
        chat_id,
        (
            "Publish finished.\n"
            f"Scheduled: {metrics.get('scheduled_count', 0)}\n"
            f"Published: {metrics.get('published_count', 0)}\n"
            f"Retry scheduled: {metrics.get('retry_scheduled_count', 0)}\n"
            f"Failed terminal: {metrics.get('failed_terminal_count', 0)}"
        ),
    )


def _extract_chat_id(update: dict[str, Any]) -> int | None:
    if "message" in update:
        chat_id = update["message"].get("chat", {}).get("id")
        return int(chat_id) if chat_id is not None else None
    if "callback_query" in update:
        chat_id = update["callback_query"].get("message", {}).get("chat", {}).get("id")
        return int(chat_id) if chat_id is not None else None
    return None


def _parse_callback_data(callback_data: str) -> tuple[str, str]:
    if ":" not in callback_data:
        return "", ""
    action, review_item_id = callback_data.split(":", 1)
    return action, review_item_id


def _get_app_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", get_settings())


def _schedule_background_task(coroutine: Any) -> asyncio.Task[Any]:
    return asyncio.create_task(coroutine)
