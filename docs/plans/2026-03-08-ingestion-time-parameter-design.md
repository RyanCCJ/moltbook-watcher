# Ingestion Time Parameter Design

Date: 2026-03-08

## Context

The ingestion pipeline previously used a local `window` abstraction such as `past_hour` or `today`. The Moltbook API request only sent `sort` and `limit`, then the application applied time filtering locally after fetching posts. This created misleading behavior when `sort=top` was used: recently published posts could exist on Moltbook but still be absent from the fetched result set because older top-ranked posts were scanned first.

## Decision

Replace the local `window` abstraction with the upstream Moltbook API `time` parameter everywhere in the ingestion path.

Supported values:
- `hour`
- `day`
- `week`
- `month`
- `all`

Telegram `/ingest` uses:
- `time=hour`
- `sort=top`
- `limit=100`

## Scope

Update the following paths to use `time` directly:
- `src/integrations/moltbook_api_client.py`
- `src/workers/ingestion_worker.py`
- `src/workers/runtime.py`
- `src/workers/scheduler.py`
- `src/api/ops_routes.py`
- `src/api/telegram_routes.py`
- `scripts/ops_cli.py`
- related tests and documentation

## Schema

Rename the database column `candidate_posts.source_window` to `candidate_posts.source_time`.

The migration path is:
- if `source_window` exists and `source_time` does not, rename the column in place
- new databases create the column as `source_time`

## Rationale

This removes an incorrect abstraction, aligns system behavior with the upstream API, and makes `fetched_count` easier to interpret. It also keeps Telegram, CLI, scheduler, and HTTP API behavior consistent.
