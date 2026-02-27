from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    publish_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="smtp_email")
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotificationEventRepository:
    async def create_pending(self, session: AsyncSession, *, publish_job_id: str, recipient: str) -> NotificationEvent:
        event = NotificationEvent(
            publish_job_id=publish_job_id,
            recipient=recipient,
            status="pending",
        )
        session.add(event)
        await session.flush()
        return event

    async def mark_sent(self, session: AsyncSession, event: NotificationEvent) -> NotificationEvent:
        event.status = "sent"
        event.sent_at = datetime.now(tz=UTC)
        session.add(event)
        await session.flush()
        return event

    async def mark_failed(
        self,
        session: AsyncSession,
        event: NotificationEvent,
        *,
        error_message: str,
    ) -> NotificationEvent:
        event.status = "failed"
        event.error_message = error_message
        session.add(event)
        await session.flush()
        return event
