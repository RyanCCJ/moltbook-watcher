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
from src.services.scoring_service import ScoringService

logger = get_logger(__name__)


@dataclass(slots=True)
class IngestionMetrics:
    fetched_count: int
    persisted_count: int
    filtered_duplicate_count: int
    elapsed_ms: int


class IngestionWorker:
    def __init__(
        self,
        *,
        moltbook_client: MoltbookAPIClient,
        scoring_service: ScoringService,
        dedup_service: DedupService | None = None,
    ) -> None:
        self._moltbook_client = moltbook_client
        self._scoring_service = scoring_service
        self._dedup_service = dedup_service or DedupService()
        self._candidate_repo = CandidatePostRepository()
        self._score_repo = ScoreCardRepository()

    async def run_cycle(
        self,
        session: AsyncSession,
        window: str = "past_hour",
        limit: int = 100,
        sort: str = "top",
    ) -> IngestionMetrics:
        started = perf_counter()
        posts, _ = await self._moltbook_client.list_posts(window=window, limit=limit, sort=sort)

        existing_texts = await self._candidate_repo.list_active_contents(session)
        persisted_count = 0
        filtered_duplicate_count = 0

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

            candidate = await self._candidate_repo.create(
                session,
                source_url=post.source_url,
                source_window=window,
                source_post_id=post.source_post_id,
                author_handle=post.author_handle,
                raw_content=post.content_text,
                captured_at=post.created_at,
                dedup_fingerprint=fingerprint,
                top_comments_snapshot=comment_snapshot,
            )

            score = await self._scoring_service.score_candidate(
                post.content_text,
                post.engagement_summary,
                post.top_comments,
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
                score_version=score.score_version,
            )

            await self._candidate_repo.transition_status(session, candidate, CandidateStatus.SCORED)
            await self._candidate_repo.transition_status(session, candidate, CandidateStatus.QUEUED)

            existing_texts.append(post.content_text)
            persisted_count += 1

        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "ingestion_cycle_completed",
            at=datetime.now(tz=UTC).isoformat(),
            fetched_count=len(posts),
            persisted_count=persisted_count,
            filtered_duplicate_count=filtered_duplicate_count,
            elapsed_ms=elapsed_ms,
        )

        return IngestionMetrics(
            fetched_count=len(posts),
            persisted_count=persisted_count,
            filtered_duplicate_count=filtered_duplicate_count,
            elapsed_ms=elapsed_ms,
        )
