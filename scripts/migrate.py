from __future__ import annotations

import asyncio

from sqlalchemy import inspect, text

from src.models.base import create_schema, get_engine

_LEGACY_PREFIX = "https://www.moltbook.com/posts/"
_CANONICAL_PREFIX = "https://www.moltbook.com/post/"


async def _ensure_review_item_columns() -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        def _read_columns(sync_connection) -> set[str]:
            table_names = inspect(sync_connection).get_table_names()
            if "review_items" not in table_names:
                return set()
            return {column["name"] for column in inspect(sync_connection).get_columns("review_items")}

        existing_columns = await connection.run_sync(_read_columns)
        migration_statements: list[str] = []

        if "top_comments_snapshot" not in existing_columns:
            migration_statements.append(
                "ALTER TABLE review_items ADD COLUMN top_comments_snapshot JSON NOT NULL DEFAULT '[]'"
            )
        if "top_comments_translated" not in existing_columns:
            migration_statements.append(
                "ALTER TABLE review_items ADD COLUMN top_comments_translated JSON NOT NULL DEFAULT '[]'"
            )
        if "threads_draft" not in existing_columns:
            migration_statements.append(
                "ALTER TABLE review_items ADD COLUMN threads_draft TEXT NOT NULL DEFAULT ''"
            )

        for statement in migration_statements:
            await connection.execute(text(statement))


async def _normalize_legacy_moltbook_urls() -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE candidate_posts
                SET source_url = REPLACE(source_url, :legacy, :canonical)
                WHERE source_url LIKE :legacy_like
                """
            ),
            {"legacy": _LEGACY_PREFIX, "canonical": _CANONICAL_PREFIX, "legacy_like": f"{_LEGACY_PREFIX}%"},
        )
        await connection.execute(
            text(
                """
                UPDATE published_post_records
                SET source_url = REPLACE(source_url, :legacy, :canonical),
                    attribution_link = REPLACE(attribution_link, :legacy, :canonical)
                WHERE source_url LIKE :legacy_like OR attribution_link LIKE :legacy_like
                """
            ),
            {"legacy": _LEGACY_PREFIX, "canonical": _CANONICAL_PREFIX, "legacy_like": f"{_LEGACY_PREFIX}%"},
        )
        await connection.execute(
            text(
                """
                UPDATE review_items
                SET threads_draft = REPLACE(threads_draft, :legacy, :canonical)
                WHERE threads_draft LIKE :legacy_contains
                """
            ),
            {"legacy": _LEGACY_PREFIX, "canonical": _CANONICAL_PREFIX, "legacy_contains": f"%{_LEGACY_PREFIX}%"},
        )


async def main() -> None:
    await create_schema()
    await _ensure_review_item_columns()
    await _normalize_legacy_moltbook_urls()


if __name__ == "__main__":
    asyncio.run(main())
