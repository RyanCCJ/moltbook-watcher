from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlparse

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
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
    redis_keys_removed: int | None = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reset Moltbook Watcher state without touching other services.")
    parser.add_argument("--target", choices=["db", "redis", "all"], default="all")
    parser.add_argument("--yes", action="store_true", help="Required to execute destructive actions.")

    parser.add_argument("--redis-mode", choices=["prefix", "flushdb"], default="prefix")
    parser.add_argument(
        "--redis-prefix",
        default="moltbook:",
        help="Key prefix when --redis-mode prefix is used.",
    )
    parser.add_argument(
        "--allow-redis-db0-flush",
        action="store_true",
        help="Allow FLUSHDB on Redis DB index 0 (normally blocked for safety).",
    )
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


async def _reset_redis(
    redis_url: str,
    *,
    mode: str,
    prefix: str,
    allow_db0_flush: bool,
) -> int:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        if mode == "flushdb":
            parsed = urlparse(redis_url)
            db_idx = 0
            if parsed.path and parsed.path != "/":
                db_idx = int(parsed.path.lstrip("/"))
            if db_idx == 0 and not allow_db0_flush:
                raise RuntimeError(
                    "Refusing FLUSHDB on Redis DB 0. Use a dedicated DB index or pass --allow-redis-db0-flush explicitly."
                )
            keys = [key async for key in client.scan_iter(match="*")]
            if keys:
                await client.flushdb()
            return len(keys)

        if not prefix:
            raise RuntimeError("Prefix mode requires non-empty --redis-prefix")
        keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
        if keys:
            await client.delete(*keys)
        return len(keys)
    finally:
        await client.aclose()


async def _run(args: argparse.Namespace) -> ResetResult:
    if not args.yes:
        raise RuntimeError("Refusing to run without --yes.")

    settings = get_settings()
    result = ResetResult()

    if args.target in {"db", "all"}:
        result.database_rows_removed = await _reset_db(settings.database_url, APP_TABLES)

    if args.target in {"redis", "all"}:
        result.redis_keys_removed = await _reset_redis(
            settings.redis_url,
            mode=args.redis_mode,
            prefix=args.redis_prefix,
            allow_db0_flush=args.allow_redis_db0_flush,
        )

    return result


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = asyncio.run(_run(args))
    except Exception as error:
        print(f"reset failed: {error}")
        return 1

    if result.database_rows_removed is not None:
        print(f"database_rows_removed={result.database_rows_removed}")
    if result.redis_keys_removed is not None:
        print(f"redis_keys_removed={result.redis_keys_removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
