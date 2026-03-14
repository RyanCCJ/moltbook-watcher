from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import reset_state


@pytest.mark.asyncio
async def test_run_resets_known_database_tables_without_redis(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "reset-state.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE candidate_posts (id TEXT PRIMARY KEY)"))
        await connection.execute(text("CREATE TABLE score_cards (id TEXT PRIMARY KEY)"))
        await connection.execute(text("INSERT INTO candidate_posts (id) VALUES ('candidate-1')"))
        await connection.execute(text("INSERT INTO score_cards (id) VALUES ('score-1')"))

    monkeypatch.setattr(
        reset_state,
        "get_settings",
        lambda: SimpleNamespace(database_url=f"sqlite+aiosqlite:///{db_path}"),
    )

    result = await reset_state._run(SimpleNamespace(yes=True))

    assert result.database_rows_removed == 2

    async with engine.begin() as connection:
        candidate_count = await connection.scalar(text("SELECT COUNT(*) FROM candidate_posts"))
        score_count = await connection.scalar(text("SELECT COUNT(*) FROM score_cards"))

    assert candidate_count == 0
    assert score_count == 0

    await engine.dispose()


def test_build_parser_accepts_yes_flag() -> None:
    parser = reset_state._build_parser()

    args = parser.parse_args(["--yes"])

    assert args.yes is True
