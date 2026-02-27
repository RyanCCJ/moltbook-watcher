from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from redis.asyncio import Redis


class QueueClient:
    def __init__(self, redis_url: str, redis_factory: Callable[[str], Redis] | None = None) -> None:
        self._redis_url = redis_url
        self._redis_factory = redis_factory or (lambda url: Redis.from_url(url, decode_responses=True))
        self._redis: Redis | None = None
        self._memory_queues: dict[str, deque[str]] = defaultdict(deque)

    async def connect(self) -> None:
        if self._redis_url.startswith("memory://"):
            return
        if self._redis is None:
            self._redis = self._redis_factory(self._redis_url)

    async def ping(self) -> bool:
        if self._redis_url.startswith("memory://"):
            return True
        await self.connect()
        assert self._redis is not None
        return bool(await self._redis.ping())

    async def enqueue(self, queue_name: str, payload: dict[str, Any]) -> None:
        message = json.dumps(payload)
        if self._redis_url.startswith("memory://"):
            self._memory_queues[queue_name].append(message)
            return
        await self.connect()
        assert self._redis is not None
        await self._redis.rpush(queue_name, message)

    async def dequeue(self, queue_name: str) -> dict[str, Any] | None:
        if self._redis_url.startswith("memory://"):
            if not self._memory_queues[queue_name]:
                return None
            return json.loads(self._memory_queues[queue_name].popleft())

        await self.connect()
        assert self._redis is not None
        message = await self._redis.lpop(queue_name)
        if message is None:
            return None
        return json.loads(message)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
