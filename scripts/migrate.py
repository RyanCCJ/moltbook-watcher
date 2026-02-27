from __future__ import annotations

import asyncio

from src.models.base import create_schema


async def main() -> None:
    await create_schema()


if __name__ == "__main__":
    asyncio.run(main())
