from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config.settings import get_settings

APP_TABLES: tuple[str, ...] = (
    "notification_events",
    "follow_up_candidates",
    "published_post_records",
    "publish_jobs",
    "review_items",
    "score_cards",
    "candidate_posts",
)


@dataclass(slots=True)
class ResetResult:
    database_rows_removed: int | None = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reset Moltbook Watcher state without touching other services.")
    parser.add_argument("--yes", action="store_true", help="Required to execute destructive actions.")
    return parser


async def _reset_db(database_url: str, table_names: Sequence[str]) -> int:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    removed_rows_estimate = 0
    try:
        async with engine.begin() as connection:
            dialect = connection.dialect.name
            if dialect == "postgresql":
                count_parts = []
                for table in table_names:
                    count_parts.append(
                        f"SELECT count(*)::bigint AS c FROM {table}"
                    )
                count_sql = " + ".join(f"({part})" for part in count_parts)
                count_result = await connection.execute(text(f"SELECT {count_sql} AS total"))
                removed_rows_estimate = int(count_result.scalar_one())

                joined = ", ".join(table_names)
                await connection.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
            elif dialect == "sqlite":
                existing_tables = set(
                    (
                        await connection.execute(
                            text("SELECT name FROM sqlite_master WHERE type='table'")
                        )
                    ).scalars()
                )
                for table in table_names:
                    if table not in existing_tables:
                        continue
                    count_result = await connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    removed_rows_estimate += int(count_result.scalar_one())
                    await connection.execute(text(f"DELETE FROM {table}"))
            else:
                raise RuntimeError(f"Unsupported DB dialect for reset: {dialect}")
    finally:
        await engine.dispose()
    return removed_rows_estimate


async def _run(args: argparse.Namespace) -> ResetResult:
    if not args.yes:
        raise RuntimeError("Refusing to run without --yes.")

    settings = get_settings()
    return ResetResult(
        database_rows_removed=await _reset_db(settings.database_url, APP_TABLES),
    )


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = asyncio.run(_run(args))
    except Exception as error:
        print(f"reset failed: {error}")
        return 1

    if result.database_rows_removed is not None:
        print(f"database_rows_removed={result.database_rows_removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
