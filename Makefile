.PHONY: api worker scheduler test lint ops-help ops-health ops-smoke

api:
	uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

worker:
	uv run python -m src.workers.scheduler

scheduler:
	uv run python -m src.workers.scheduler

test:
	uv run pytest

lint:
	uv run ruff check .

ops-help:
	uv run python scripts/ops_cli.py --help

ops-health:
	uv run python scripts/ops_cli.py health

ops-smoke:
	uv run python scripts/ops_cli.py smoke --approve --limit 1
