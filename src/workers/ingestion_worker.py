from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.moltbook_api_client import MoltbookAPIClient
from src.models.candidate_post import CandidatePostRepository
from src.models.lifecycle import CandidateStatus
from src.models.score_card import ScoreCardRepository
from src.services.dedup_service import DedupService
from src.services.logging_service import get_logger
from src.services.publish_mode_service import PublishControlService, publish_control
from src.services.routing_service import RoutingService
from src.services.scoring_service import ScoringService

logger = get_logger(__name__)


@dataclass(slots=True)
class IngestionMetrics:
    fetched_count: int
    persisted_count: int
    scored_count: int
    queued_count: int
    archived_count: int
    auto_approved_count: int
    fast_track_count: int
    filtered_duplicate_count: int
    score_breakdown: dict[str, int]
    risk_breakdown: dict[str, int]
    elapsed_ms: int


class IngestionWorker:
    def __init__(
        self,
        *,
        moltbook_client: MoltbookAPIClient,
        scoring_service: ScoringService,
        dedup_service: DedupService | None = None,
        routing_service: RoutingService | None = None,
        control_service: PublishControlService | None = None,
        review_min_score: float = 3.5,
    ) -> None:
        self._moltbook_client = moltbook_client
        self._scoring_service = scoring_service
        self._dedup_service = dedup_service or DedupService()
        self._routing_service = routing_service or RoutingService()
        self._control_service = control_service or publish_control
        self._review_min_score = review_min_score
        self._candidate_repo = CandidatePostRepository()
        self._score_repo = ScoreCardRepository()

    async def run_cycle(
        self,
        session: AsyncSession,
        time: str = "hour",
        limit: int = 100,
        sort: str = "top",
    ) -> IngestionMetrics:
        started = perf_counter()
        posts, _ = await self._moltbook_client.list_posts(time=time, limit=limit, sort=sort)

        existing_texts = await self._candidate_repo.list_active_contents(session)
        persisted_count = 0
        scored_count = 0
        queued_count = 0
        archived_count = 0
        auto_approved_count = 0
        fast_track_count = 0
        filtered_duplicate_count = 0
        score_breakdown = {"auto_publish": 0, "review_queue": 0, "archived": 0}
        risk_breakdown = {"low": 0, "medium": 0, "high": 0}

        for post in posts:
            existing = await self._candidate_repo.get_by_source_url(session, post.source_url)
            if existing is not None:
                filtered_duplicate_count += 1
                continue

            if self._dedup_service.should_filter(post.content_text, existing_texts):
                filtered_duplicate_count += 1
                continue

            if post.source_post_id:
                post.top_comments = await self._moltbook_client.fetch_comments(post.source_post_id, limit=5, sort="top")

            fingerprint = self._dedup_service.build_fingerprint(post.content_text)
            comment_snapshot = [
                {
                    "author_handle": comment.author_handle,
                    "content_text": comment.content_text,
                    "upvotes": comment.upvotes,
                }
                for comment in post.top_comments
            ]

            post_upvotes = post.upvotes
            if not post_upvotes and isinstance(post.engagement_summary, dict):
                try:
                    post_upvotes = max(0, int(post.engagement_summary.get("upvotes", 0)))
                except (TypeError, ValueError):
                    pass

            candidate = await self._candidate_repo.create(
                session,
                source_url=post.source_url,
                source_time=time,
                source_post_id=post.source_post_id,
                author_handle=post.author_handle,
                raw_content=post.content_text,
                captured_at=post.created_at,
                dedup_fingerprint=fingerprint,
                top_comments_snapshot=comment_snapshot,
                post_upvotes=post_upvotes,
            )

            score = await self._scoring_service.score_candidate(
                post.content_text,
                post.engagement_summary,
                post.top_comments,
            )
            route_decision = self._routing_service.route_candidate(
                final_score=score.final_score,
                risk_score=score.risk,
            )
            await self._score_repo.create(
                session,
                candidate_post_id=candidate.id,
                novelty_score=score.novelty,
                depth_score=score.depth,
                tension_score=score.tension,
                reflective_impact_score=score.reflective_impact,
                engagement_score=score.engagement,
                risk_score=score.risk,
                content_score=score.content_score,
                final_score=score.final_score,
                route_decision=route_decision,
                score_version=score.score_version,
            )

            await self._candidate_repo.transition_status(session, candidate, CandidateStatus.SCORED)
            scored_count += 1

            if score.final_score >= self._routing_service.fast_track_min_score:
                score_breakdown["auto_publish"] += 1
            elif score.final_score >= self._review_min_score:
                score_breakdown["review_queue"] += 1
            else:
                score_breakdown["archived"] += 1

            if score.risk >= self._routing_service.high_risk_threshold:
                risk_breakdown["high"] += 1
            elif score.risk >= 2:
                risk_breakdown["medium"] += 1
            else:
                risk_breakdown["low"] += 1

            if route_decision == "fast_track":
                fast_track_count += 1

            if score.final_score < self._review_min_score:
                await self._candidate_repo.transition_status(session, candidate, CandidateStatus.ARCHIVED)
                archived_count += 1
            else:
                await self._candidate_repo.transition_status(session, candidate, CandidateStatus.QUEUED)
                queued_count += 1
                if route_decision == "fast_track" and self._control_service.can_auto_publish(risk_score=score.risk):
                    await self._candidate_repo.transition_status(session, candidate, CandidateStatus.APPROVED)
                    auto_approved_count += 1

            existing_texts.append(post.content_text)
            persisted_count += 1

        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "ingestion_cycle_completed",
            at=datetime.now(tz=UTC).isoformat(),
            fetched_count=len(posts),
            persisted_count=persisted_count,
            scored_count=scored_count,
            queued_count=queued_count,
            archived_count=archived_count,
            auto_approved_count=auto_approved_count,
            filtered_duplicate_count=filtered_duplicate_count,
            elapsed_ms=elapsed_ms,
        )

        return IngestionMetrics(
            fetched_count=len(posts),
            persisted_count=persisted_count,
            scored_count=scored_count,
            queued_count=queued_count,
            archived_count=archived_count,
            auto_approved_count=auto_approved_count,
            fast_track_count=fast_track_count,
            filtered_duplicate_count=filtered_duplicate_count,
            score_breakdown=score_breakdown,
            risk_breakdown=risk_breakdown,
            elapsed_ms=elapsed_ms,
        )
