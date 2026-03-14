.PHONY: api worker scheduler test lint reset ops-help ops-health ops-smoke ops-regenerate

api:
	uv run uvicorn src.api.app:app --reload --host 127.0.0.1 --port 8000

worker:
	uv run python -m src.workers.scheduler

test:
	uv run pytest

lint:
	uv run ruff check .

reset:
	uv run python scripts/reset_state.py --yes

ops-help:
	uv run python scripts/ops_cli.py --help

ops-health:
	uv run python scripts/ops_cli.py health

ops-smoke:
	uv run python scripts/ops_cli.py smoke --approve --limit 1

ops-regenerate:
	uv run python scripts/ops_cli.py regenerate
