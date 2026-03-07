from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from src.integrations.telegram_client import TelegramClient

MAX_TELEGRAM_MESSAGE_LENGTH = 4096
MAX_CONTENT_LENGTH = 800
CONTENT_TRUNCATION_SUFFIX = "… (full content omitted)"


class TelegramService:
    def __init__(self, telegram_client: TelegramClient, chat_id: str) -> None:
        self._telegram_client = telegram_client
        self._chat_id = chat_id
        self._pending_comments: dict[int, str] = {}
        self._pending_edits: dict[int, str] = {}
        self._pending_comment_context: dict[int, tuple[int, str]] = {}

    def format_review_message(self, review_item_data: dict[str, Any]) -> str:
        review_item_id = str(review_item_data.get("id", "unknown"))
        content = self._select_content(review_item_data)
        score_value = self._get_final_score(review_item_data)
        risk_tags = review_item_data.get("riskTags") or []
        source_url = str(review_item_data.get("sourceUrl") or "")

        risk_text = ", ".join(str(tag) for tag in risk_tags) if risk_tags else "none"
        header = f"<b>Review item</b> <code>{escape(review_item_id)}</code>"
        lines = [
            header,
            f"<b>Draft</b>\n{escape(self._truncate_content(content))}",
            f"<b>Final score:</b> {escape(score_value)}",
            f"<b>Risk tags:</b> {escape(risk_text)}",
        ]
        if source_url:
            escaped_url = escape(source_url, quote=True)
            lines.append(f'<b>Source:</b> <a href="{escaped_url}">{escaped_url}</a>')
        return self._enforce_message_limit("\n\n".join(lines), content)

    def build_review_inline_keyboard(self, review_item_id: str) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": f"approve:{review_item_id}"},
                    {"text": "Reject", "callback_data": f"reject:{review_item_id}"},
                ],
                [
                    {"text": "Reject+Comment", "callback_data": f"comment:{review_item_id}"},
                    {"text": "Edit Draft", "callback_data": f"edit:{review_item_id}"},
                ],
            ]
        }

    async def push_pending_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        responses: list[dict[str, Any]] = []
        for item in items:
            response = await self._telegram_client.send_message(
                self._chat_id,
                self.format_review_message(item),
                reply_markup=self.build_review_inline_keyboard(str(item["id"])),
            )
            responses.append(response)
        return responses

    async def update_message_with_decision(
        self,
        chat_id: str,
        message_id: int,
        original_text: str,
        decision: str,
        timestamp: str | datetime,
        comment: str | None = None,
    ) -> dict[str, Any]:
        rendered_timestamp = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        lines = [
            original_text,
            "",
            f"<b>Decision:</b> {escape(decision)}",
            f"<b>At:</b> {escape(rendered_timestamp)}",
        ]
        if comment:
            lines.append(f"<b>Comment:</b> {escape(comment)}")
        return await self._telegram_client.edit_message_text(chat_id, message_id, "\n".join(lines))

    def set_pending_comment(
        self,
        chat_id: int,
        review_item_id: str,
        *,
        message_id: int | None = None,
        original_text: str | None = None,
    ) -> None:
        self._pending_edits.pop(chat_id, None)
        self._pending_comments[chat_id] = review_item_id
        if message_id is not None and original_text is not None:
            self._pending_comment_context[chat_id] = (message_id, original_text)
        else:
            self._pending_comment_context.pop(chat_id, None)

    def get_pending_comment(self, chat_id: int) -> str | None:
        return self._pending_comments.get(chat_id)

    def get_pending_comment_context(self, chat_id: int) -> tuple[int, str] | None:
        return self._pending_comment_context.get(chat_id)

    def clear_pending_comment(self, chat_id: int) -> None:
        self._pending_comments.pop(chat_id, None)
        self._pending_comment_context.pop(chat_id, None)

    def set_pending_edit(self, chat_id: int, review_item_id: str) -> None:
        self._pending_comments.pop(chat_id, None)
        self._pending_comment_context.pop(chat_id, None)
        self._pending_edits[chat_id] = review_item_id

    def get_pending_edit(self, chat_id: int) -> str | None:
        return self._pending_edits.get(chat_id)

    def clear_pending_edit(self, chat_id: int) -> None:
        self._pending_edits.pop(chat_id, None)

    def clear_pending_state(self, chat_id: int) -> bool:
        cleared = False
        if chat_id in self._pending_comments:
            self._pending_comments.pop(chat_id, None)
            self._pending_comment_context.pop(chat_id, None)
            cleared = True
        if chat_id in self._pending_edits:
            self._pending_edits.pop(chat_id, None)
            cleared = True
        return cleared

    def format_pending_list(self, items: list[dict[str, Any]]) -> str:
        if not items:
            return "No pending review items."

        visible_items = items[:10]
        lines = ["<b>Pending review items</b>"]
        for index, item in enumerate(visible_items, start=1):
            title = self._summarize_pending_item(item)
            score = self._get_final_score(item)
            risk_tags = item.get("riskTags") or []
            risk_text = ", ".join(str(tag) for tag in risk_tags) if risk_tags else "none"
            lines.append(f"{index}. {escape(title)} | score {escape(score)} | risk {escape(risk_text)}")
        remaining = len(items) - len(visible_items)
        if remaining > 0:
            lines.append(f"… and {remaining} more")
        lines.append("")
        lines.append("Use /review &lt;number&gt; to open full details.")
        return "\n".join(lines)

    def build_review_detail_messages(
        self,
        review_item_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        review_item_id = str(review_item_data.get("id", "unknown"))
        score_value = self._get_final_score(review_item_data)
        risk_tags = review_item_data.get("riskTags") or []
        risk_text = ", ".join(str(tag) for tag in risk_tags) if risk_tags else "none"
        source_url = str(review_item_data.get("sourceUrl") or "")
        follow_up_rationale = str(review_item_data.get("followUpRationale") or "").strip()

        header_lines = [
            f"<b>Review item</b> <code>{escape(review_item_id)}</code>",
            f"<b>Final score:</b> {escape(score_value)}",
            f"<b>Risk tags:</b> {escape(risk_text)}",
        ]
        if source_url:
            escaped_url = escape(source_url, quote=True)
            header_lines.append(f'<b>Source:</b> <a href="{escaped_url}">{escaped_url}</a>')
        if follow_up_rationale:
            header_lines.append(f"<b>Follow-up rationale:</b>\n{escape(follow_up_rationale)}")

        messages = [{"text": "\n\n".join(header_lines), "reply_markup": None}]
        messages.extend(self._build_section_messages("<b>Original draft</b>", review_item_data.get("draftContent")))
        messages.extend(self._build_section_messages("<b>Translated draft</b>", review_item_data.get("translatedContent")))
        messages.extend(
            self._build_section_messages(
                "<b>Comments (original)</b>",
                self._format_comment_section(review_item_data.get("topCommentsSnapshot")),
            )
        )
        messages.extend(
            self._build_section_messages(
                "<b>Comments (translated)</b>",
                self._format_comment_section(review_item_data.get("topCommentsTranslated")),
            )
        )

        thread_messages = self._build_section_messages("<b>Threads draft</b>", review_item_data.get("threadsDraft"))
        if thread_messages:
            thread_messages[-1]["reply_markup"] = self.build_review_inline_keyboard(review_item_id)
            messages.extend(thread_messages)
        else:
            messages.append(
                {
                    "text": "<b>Threads draft</b>\n(no draft available)",
                    "reply_markup": self.build_review_inline_keyboard(review_item_id),
                }
            )
        return messages

    def format_stats_message(self, stats_data: dict[str, Any]) -> str:
        top_pending = stats_data.get("topPendingItems") or []
        lines = [
            "<b>Pipeline stats</b>",
            f"Pending: {stats_data.get('pendingCount', 0)}",
            f"Approved today: {stats_data.get('approvedTodayCount', 0)}",
            f"Rejected today: {stats_data.get('rejectedTodayCount', 0)}",
            f"Published today: {stats_data.get('publishedTodayCount', 0)}",
        ]
        if "ingestedTodayCount" in stats_data:
            lines.append(f"Ingested today: {stats_data.get('ingestedTodayCount', 0)}")
        if "failedJobCount" in stats_data:
            lines.append(f"Failed jobs today: {stats_data.get('failedJobCount', 0)}")
        if top_pending:
            lines.append("")
            lines.append("<b>Top pending</b>")
            for item in top_pending[:3]:
                title = self._truncate_line(self._select_content(item), 60)
                lines.append(f"- {escape(title)} ({escape(self._get_final_score(item))})")
        else:
            lines.append("")
            lines.append("No pending items")
        return "\n".join(lines)

    def format_health_message(self, health_data: dict[str, Any]) -> str:
        errors = health_data.get("errors") or []
        lines = [
            "<b>System health</b>",
            f"Status: {escape(str(health_data.get('status', 'unknown')))}",
            f"Database: {self._format_boolean(health_data.get('database'))}",
            f"Queue: {self._format_boolean(health_data.get('queue'))}",
        ]
        if "webhook" in health_data:
            lines.append(f"Webhook: {self._format_boolean(health_data.get('webhook'))}")
        if errors:
            lines.append("")
            lines.append("<b>Errors</b>")
            lines.extend(f"- {escape(str(error))}" for error in errors)
        return "\n".join(lines)

    def format_help_message(self) -> str:
        return "\n".join(
            [
                "<b>Available commands</b>",
                "/pending - Show pending review items",
                "/review &lt;number&gt; - Show full details for one pending item",
                "/ingest [time] [sort] [limit] - Start ingestion; tokens can be in any order",
                "/publish - Start one publish cycle",
                "/stats - Show pipeline stats",
                "/health - Show system health",
                "/help - Show this help message",
                "/cancel - Cancel the current comment or edit flow",
            ]
        )

    def _select_content(self, review_item_data: dict[str, Any]) -> str:
        for key in ("threadsDraft", "translatedContent", "draftContent"):
            value = review_item_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "(no draft available)"

    def _get_final_score(self, review_item_data: dict[str, Any]) -> str:
        ai_score = review_item_data.get("aiScore") or {}
        final_score = ai_score.get("finalScore")
        if final_score is None:
            return "n/a"
        return str(final_score)

    def _truncate_content(self, text: str) -> str:
        if len(text) <= MAX_CONTENT_LENGTH:
            return text
        available = MAX_CONTENT_LENGTH - len(CONTENT_TRUNCATION_SUFFIX)
        return f"{text[:available].rstrip()}{CONTENT_TRUNCATION_SUFFIX}"

    def _enforce_message_limit(self, message: str, original_content: str) -> str:
        if len(message) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            return message

        overflow = len(message) - MAX_TELEGRAM_MESSAGE_LENGTH
        extra_trim = overflow + len(CONTENT_TRUNCATION_SUFFIX)
        trimmed_content = original_content[:-extra_trim] if extra_trim < len(original_content) else ""
        message = message.replace(
            escape(self._truncate_content(original_content)),
            escape(f"{trimmed_content.rstrip()}{CONTENT_TRUNCATION_SUFFIX}" if trimmed_content else CONTENT_TRUNCATION_SUFFIX),
            1,
        )
        return message[:MAX_TELEGRAM_MESSAGE_LENGTH]

    def _truncate_line(self, text: str, limit: int) -> str:
        first_line = text.splitlines()[0].strip() if text else "(no draft available)"
        if len(first_line) <= limit:
            return first_line
        return f"{first_line[: limit - 1].rstrip()}…"

    def _summarize_pending_item(self, review_item_data: dict[str, Any]) -> str:
        summary = self._extract_first_sentence(self._select_content(review_item_data))
        if summary:
            return self._truncate_line(summary, 160)
        return self._truncate_line(self._select_content(review_item_data), 160)

    def _extract_first_sentence(self, text: str) -> str:
        normalized = " ".join(text.split())
        for separator in (". ", "! ", "? ", "。", "！", "？"):
            if separator in normalized:
                first_part = normalized.split(separator, 1)[0].strip()
                if first_part:
                    if separator in {". ", "! ", "? "}:
                        return f"{first_part}{separator.strip()}"
                    return f"{first_part}{separator}"
        return normalized

    def _build_section_messages(self, title: str, content: Any) -> list[dict[str, Any]]:
        text = str(content or "").strip() or "(none)"
        available_length = MAX_TELEGRAM_MESSAGE_LENGTH - len(title) - 2
        chunks = self._chunk_text(text, available_length)
        messages: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks, start=1):
            header = title if len(chunks) == 1 else f"{title} ({index}/{len(chunks)})"
            messages.append({"text": f"{header}\n{escape(chunk)}", "reply_markup": None})
        return messages

    def _chunk_text(self, text: str, max_length: int) -> list[str]:
        if len(text) <= max_length:
            return [text]
        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, max_length)
            if split_at == -1:
                split_at = remaining.rfind(" ", 0, max_length)
            if split_at == -1 or split_at < max_length // 2:
                split_at = max_length
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        return chunks

    def _format_comment_section(self, comments: Any) -> str:
        if not comments:
            return "(none)"
        lines: list[str] = []
        for index, comment in enumerate(comments, start=1):
            if isinstance(comment, dict):
                author = str(comment.get("author_handle") or "unknown")
                content = str(
                    comment.get("content_text")
                    or comment.get("content")
                    or comment.get("text")
                    or ""
                ).strip()
                upvotes = comment.get("upvotes")
                line = f"{index}. @{author}"
                if upvotes is not None:
                    line += f" ({upvotes} upvotes)"
                if content:
                    line += f"\n{content}"
                lines.append(line)
                continue
            lines.append(f"{index}. {str(comment)}")
        return "\n\n".join(lines)

    def _format_boolean(self, value: Any) -> str:
        return "ok" if value else "failed"
