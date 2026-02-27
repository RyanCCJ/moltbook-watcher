from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.notification_client import NotificationClient
from src.models.notification_event import NotificationEventRepository
from src.models.publish_job import PublishJob


class NotificationService:
    def __init__(self, client: NotificationClient, default_recipient: str) -> None:
        self._client = client
        self._default_recipient = default_recipient
        self._event_repo = NotificationEventRepository()

    async def notify_terminal_failure(
        self,
        session: AsyncSession,
        publish_job: PublishJob,
        error_message: str,
    ) -> None:
        event = await self._event_repo.create_pending(
            session,
            publish_job_id=publish_job.id,
            recipient=self._default_recipient,
        )
        subject = "Moltbook publish job terminal failure"
        body = f"Publish job {publish_job.id} failed terminally. Error: {error_message}"

        try:
            await self._client.send_notification(subject, body)
        except Exception as error:
            await self._event_repo.mark_failed(session, event, error_message=str(error))
            return

        await self._event_repo.mark_sent(session, event)
