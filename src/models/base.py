from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config.settings import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_engine: AsyncEngine = create_async_engine(_settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)


def get_engine() -> AsyncEngine:
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def check_db_health(session: AsyncSession) -> bool:
    result = await session.execute(text("SELECT 1"))
    return result.scalar_one() == 1


async def create_schema() -> None:
    # Ensure all model modules are imported so metadata is populated before create_all().
    from src.models import (  # noqa: F401
        candidate_post,
        follow_up_candidate,
        notification_event,
        publish_job,
        published_post_record,
        review_item,
        score_card,
    )

    async with _engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
