from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import migrate


@pytest.mark.asyncio
async def test_candidate_post_migration_renames_source_window_to_source_time(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migrate.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE candidate_posts (
                    id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    source_window TEXT NOT NULL,
                    source_post_id TEXT,
                    author_handle TEXT,
                    raw_content TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dedup_fingerprint TEXT NOT NULL,
                    is_follow_up_candidate BOOLEAN NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
        )

    monkeypatch.setattr(migrate, "get_engine", lambda: engine)

    await migrate._ensure_candidate_post_columns()

    async with engine.begin() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: {column["name"] for column in inspect(sync_connection).get_columns("candidate_posts")}
        )

    assert "source_time" in columns
    assert "source_window" not in columns
    assert "top_comments_snapshot" in columns

    await engine.dispose()


@pytest.mark.asyncio
async def test_score_card_migration_adds_route_decision_column(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migrate-score-cards.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE score_cards (
                    id TEXT PRIMARY KEY,
                    candidate_post_id TEXT NOT NULL,
                    novelty_score FLOAT NOT NULL,
                    depth_score FLOAT NOT NULL,
                    tension_score FLOAT NOT NULL,
                    reflective_impact_score FLOAT NOT NULL,
                    engagement_score FLOAT NOT NULL,
                    risk_score INTEGER NOT NULL,
                    content_score FLOAT NOT NULL,
                    final_score FLOAT NOT NULL,
                    score_version TEXT NOT NULL,
                    scored_at TEXT NOT NULL
                )
                """
            )
        )

    monkeypatch.setattr(migrate, "get_engine", lambda: engine)

    await migrate._ensure_score_card_columns()

    async with engine.begin() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: {column["name"] for column in inspect(sync_connection).get_columns("score_cards")}
        )

    assert "route_decision" in columns

    await engine.dispose()
