## Context

The moltbook-watcher pipeline currently has a flat architecture: every ingested post receives identical treatment (score → translate → generate Threads draft → create review item → push to Telegram). RoutingService and PublishControlService exist as fully implemented but isolated modules with no callers in the pipeline. Empirical data from 397 posts shows the scoring model produces a narrow range (1.46–3.65), rendering all threshold-based gates (fast-track ≥ 4.2, draft ≥ 3.5) either unreachable or overly permissive. All ingestion parameters (time=hour, limit=100, sort=top) are hardcoded across scheduler, runtime, and API entry points with inconsistent defaults (ops API uses limit=20).

Key files involved:
- `src/workers/ingestion_worker.py` — fetch, dedup, score; currently sends all posts to QUEUED
- `src/workers/review_worker.py` — builds review payloads (translate + draft) for all QUEUED posts
- `src/workers/runtime.py` — orchestrates ingestion + review + Telegram push
- `src/workers/scheduler.py` — APScheduler cron/interval jobs
- `src/services/routing_service.py` — 30 lines, route_candidate() + is_follow_up_allowed(), zero callers
- `src/services/publish_mode_service.py` — 41 lines, can_auto_publish() never called by any worker
- `src/models/lifecycle.py` — state machine, missing SCORED→ARCHIVED and QUEUED→APPROVED transitions
- `src/config/settings.py` — pydantic Settings, currently 5 env vars for pipeline control

## Goals / Non-Goals

**Goals:**
- Make all ingestion parameters and score thresholds configurable via environment variables, enabling iterative calibration without code changes
- Skip the expensive LLM pipeline (translation + draft generation) for low-scoring posts, directly archiving them while retaining full content for traceability
- Wire RoutingService into the pipeline so route decisions are recorded and actionable
- Enable a semi-auto publish path where qualified posts (high score + low risk) can bypass human review
- Replace per-item Telegram push notifications with a single digest summary per cycle
- Unify default parameters across all entry points (scheduler, API, Telegram, CLI)

**Non-Goals:**
- Recalibrating the scoring model or adjusting LLM prompts (that requires separate experimentation)
- Implementing Shadow Mode (observation-only mode where auto-approve decisions are logged but not executed)
- Adding cursor-based pagination for ingestion (currently limit-based, sufficient for hourly scanning)
- Changing the Threads draft generation prompt or translation quality
- Multi-source ingestion (non-Moltbook sources)

## Decisions

### 1. New Settings fields

Add to `Settings` (pydantic-settings, read from `.env`):

| Variable | Type | Default | Rationale |
|----------|------|---------|-----------|
| `INGESTION_TIME` | `str` (hour/day/week/month/all) | `"hour"` | Matches current default; operator sets `all` or `month` during bootstrap phase |
| `INGESTION_LIMIT` | `int` (1–200) | `20` | Keeps inference under ~15 min; operator can override via Telegram/CLI |
| `INGESTION_SORT` | `str` (hot/new/top/rising) | `"top"` | Matches current default |
| `REVIEW_MIN_SCORE` | `float` | `3.5` | Posts below this are archived; calibratable as scoring model evolves |
| `AUTO_PUBLISH_MIN_SCORE` | `float` | `4.0` | Minimum score for semi-auto path; intentionally set above current max (3.65) so it is initially inert |

`publish_mode` Literal type changes from `"manual-approval" | "low-risk-auto"` to `"manual-approval" | "semi-auto"`.

**Alternative considered**: A single `SCORE_THRESHOLD` controlling both review gating and auto-publish. Rejected because review gating and auto-publish are fundamentally different trust levels that need independent tuning.

### 2. Low-score post lifecycle: SCORED → ARCHIVED

Posts with `final_score < REVIEW_MIN_SCORE` transition `seen → scored → archived`:

- `raw_content` is stored in full (not truncated). Storage cost is negligible (~1.5 KB/post, ~27 MB/year at 50 posts/day) and keeping full content preserves traceability, enables re-scoring if the model changes, and keeps semantic dedup fully functional.
- `score_card` is created with full scoring data (all dimensions + final_score).
- `top_comments_snapshot` is stored as-is (small JSON, useful for scoring audit).
- No `review_item` is created — no translation, no draft, no Telegram notification.
- These posts are excluded from `/recall` since no review_item exists.
- The real cost savings come from skipping 1–2 LLM calls per post (translation + draft), not from reducing text storage.

Lifecycle transition map additions:
```
SCORED → {QUEUED, ARCHIVED}   # was: SCORED → {QUEUED}
QUEUED → {REVIEWED, ARCHIVED, APPROVED}  # add APPROVED for semi-auto
```

**Alternative considered**: Not storing low-score posts at all. Rejected because source_url dedup requires the candidate record to exist, and score analytics benefit from keeping the score_card.

**Alternative considered**: Truncating raw_content to ~200 chars. Rejected because storage savings are negligible (~23 MB/year) while losing traceability, semantic dedup effectiveness, and the ability to re-score posts after model recalibration.

### 3. RoutingService integration point

Insert RoutingService call in `IngestionWorker.run_cycle()` immediately after scoring, before lifecycle transitions:

```
score = await scoring_service.score_candidate(...)
await score_repo.create(session, ...)

# NEW: routing decision
route = routing_service.route_candidate(
    final_score=score.final_score,
    risk_score=score.risk,
)

if score.final_score < review_min_score:
    # transition to archived (full content retained)
    ...
elif route == "fast_track" and publish_mode == "semi-auto":
    # transition queued → approved (skip human review)
    ...
else:
    # normal path: queued → telegram digest
    ...
```

The `route_decision` string is stored on `score_cards` as a new VARCHAR(32) column. This keeps routing data co-located with scoring data and avoids a separate table.

**Why not store on candidate_post?** The route decision is a function of the score, so it logically belongs with the score_card. If the scoring model is recalibrated and posts are re-scored, the route decision should update along with the score.

**Remove `RoutingService.is_follow_up_allowed()`**: This method duplicates `FollowUpService.evaluate()` which returns a richer `FollowUpEvaluation` dataclass. The RoutingService method has zero callers. Remove it and keep FollowUpService as the single source for follow-up logic.

### 4. Semi-auto publish path

When `PUBLISH_MODE=semi-auto`, RoutingService returns `fast_track`, and `final_score >= AUTO_PUBLISH_MIN_SCORE`:

1. IngestionWorker transitions candidate: `seen → scored → queued → approved` (skipping REVIEWED)
2. ReviewWorker still creates a review_item (with translation + draft) — needed for PublishWorker to find the threads_draft
3. PublishWorker picks up the APPROVED candidate normally (no changes needed)
4. Digest summary reports these as "auto-approved" in a separate line

This design means the ReviewWorker must still process semi-auto candidates (it needs to generate the threads_draft for publishing). The optimization is skipping human review, not skipping content generation.

**Why not skip ReviewWorker too?** PublishWorker currently uses `review_item.threads_draft` as the publish text. Without a review_item, it would fall back to raw_content, which is unformatted original Moltbook text — not suitable for Threads. We keep the ReviewWorker in the loop to produce proper drafts.

**Lifecycle transition `QUEUED → APPROVED`**: Currently the only path to APPROVED is through REVIEWED. The new direct path supports automation. For audit clarity, auto-approved candidates can be identified by having decision=`approved` with reviewed_by=`semi-auto` on their review_item.

### 5. Telegram notification reform

Replace `push_pending_items()` call in `runtime.run_ingestion_once()` with a new `format_ingestion_digest()` message:

```
📊 Ingestion Summary

Fetched: 45 | New: 12 | Filtered: 33

Score breakdown:
  ⭐ >= 4.0: 0 posts
  ✅ >= 3.5: 8 posts (queued)
  📦 < 3.5: 4 posts (archived)

Risk: Low 12

Auto-publish: 0 would qualify
Pending review: 23 total

/pending to review
```

The digest is sent only when there are new persisted posts (`persisted_count > 0`). Zero-result cycles are silent.

**Alternative considered**: Sending digest on every cycle regardless. Rejected because hourly "nothing new" messages add noise.

### 6. Entry point parameter unification

All entry points read defaults from Settings:

| Entry point | Current defaults | New behavior |
|-------------|-----------------|--------------|
| `scheduler.py` | hardcoded `time="hour"` | `settings.ingestion_time` |
| `runtime.run_ingestion_once()` | params `time="hour", limit=100, sort="top"` | read from settings |
| `ops_routes.py` | `limit=20` | `settings.ingestion_limit` |
| `telegram_routes.py` | `_DEFAULT_INGEST_*` constants | read from settings; user args override |
| CLI `ops_cli.py` | user must specify | defaults from settings |

Telegram `/ingest` preserves override capability: `/ingest all top 100` overrides settings for that single run.

## Risks / Trade-offs

**[Risk] AUTO_PUBLISH_MIN_SCORE=4.0 is currently unreachable (max observed score is 3.65)**
→ Mitigation: This is intentional. The semi-auto path is structurally ready but effectively disabled until scoring calibration produces a wider range. The operator can lower the threshold via env var once they have confidence in the scoring model. The ingestion digest's "auto-publish readiness" line provides ongoing visibility into how many posts would qualify.

**[Risk] BREAKING change to PublishMode enum (low-risk-auto → semi-auto)**
→ Mitigation: The only consumer of this value is `settings.py` Literal type and `publish_mode_service.py` switch_mode validation. Update both, and update any existing `.env` files. No database column stores this value (it's runtime state only).

**[Risk] ReviewWorker still processes semi-auto posts (translation + draft overhead)**
→ Trade-off accepted: Skipping ReviewWorker for semi-auto posts would require PublishWorker to generate drafts itself or publish raw content. The current design keeps the pipeline simple and ensures published content quality. This can be optimized later if semi-auto volume grows significantly.

**[Risk] `list_active_contents()` loads ALL candidate raw_content into memory for dedup**
→ Known pre-existing issue, not introduced by this change. Full raw_content is retained for all posts (including archived low-score ones), so dedup behavior is unchanged. A proper fix (e.g., DB-side similarity, fingerprint comparison) is out of scope.
