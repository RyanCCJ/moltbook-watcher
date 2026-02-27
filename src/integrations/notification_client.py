from __future__ import annotations

import asyncio
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage


class NotificationClient(ABC):
    @abstractmethod
    async def send_notification(self, subject: str, body: str) -> None:
        raise NotImplementedError


class SMTPNotificationClient(NotificationClient):
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        recipient: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._recipient = recipient

    async def send_notification(self, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_blocking, subject, body)

    def _send_blocking(self, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._sender
        message["To"] = self._recipient
        message.set_content(body)

        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            if self._username:
                smtp.starttls()
                smtp.login(self._username, self._password)
            smtp.send_message(message)
