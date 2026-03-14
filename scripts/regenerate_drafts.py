"""
Force-regenerate Threads drafts for any posts in the database that have a ReviewItem.

Usage:
  uv run python scripts/regenerate_drafts.py                       # regenerate ALL posts with a review item
  uv run python scripts/regenerate_drafts.py <post_id>...          # regenerate specific posts by candidate_post_id

Covered statuses: queued, approved, scheduled, retry_scheduled (i.e. everything except published/rejected/archived).
"""

import asyncio
import logging
import sys

from sqlalchemy import select

from src.config.settings import Settings
from src.integrations.moltbook_api_client import MoltbookAPIClient
from src.models.base import AsyncSessionLocal
from src.models.candidate_post import CandidatePost
from src.models.review_item import ReviewItem
from src.services.review_payload_service import ReviewPayloadService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# All statuses that still have an active review item worth regenerating
TARGET_STATUSES = ["queued", "approved", "scheduled", "retry_scheduled"]


async def regenerate_drafts(target_ids: list[str] | None = None) -> None:
    settings = Settings()

    ollama_kwargs = {}
    if settings.ollama_base_url:
        ollama_kwargs["ollama_base_url"] = settings.ollama_base_url

    client = MoltbookAPIClient(base_url=settings.moltbook_api_base_url, token=settings.moltbook_api_token)
    review_service = ReviewPayloadService(
        **ollama_kwargs,
        ollama_model=settings.ollama_model,
        use_ollama=True,
        translation_language=settings.translation_language,
        threads_language=settings.threads_language,
    )

    async with AsyncSessionLocal() as session:
        stmt = (
            select(CandidatePost, ReviewItem)
            .join(ReviewItem, CandidatePost.id == ReviewItem.candidate_post_id)
            .where(CandidatePost.status.in_(TARGET_STATUSES))
            .order_by(CandidatePost.captured_at.desc())
        )

        if target_ids:
            stmt = stmt.where(CandidatePost.id.in_(target_ids))

        results = (await session.execute(stmt)).all()

        if not results:
            logger.info("No matching posts found.")
            return

        logger.info("Found %d post(s) to regenerate.", len(results))
        updated_count = 0
        failed_count = 0

        for post, review in results:
            logger.info(
                "Regenerating post %s (status: %s, current draft length: %d)",
                post.id, post.status, len(review.threads_draft),
            )

            top_comments = []
            if post.source_post_id:
                try:
                    top_comments = await client.fetch_comments(post_id=post.source_post_id, limit=5)
                except Exception as e:
                    logger.warning("Failed to fetch comments for post %s: %s", post.id, e)

            source_url = f"https://www.moltbook.com/post/{post.source_post_id or post.id}"

            new_draft = await review_service._generate_threads_draft(
                raw_content=post.raw_content,
                top_comments=top_comments,
                final_score=4.0,
                source_url=source_url,
            )

            if new_draft and not new_draft.startswith("【 System:"):
                logger.info("✅ New draft (%d chars):\n%s\n", len(new_draft), new_draft)
                review.threads_draft = new_draft
                session.add(review)
                updated_count += 1
            else:
                logger.warning("❌ Failed to generate a valid draft for post %s — keeping existing draft.", post.id)
                failed_count += 1

        if updated_count > 0:
            await session.commit()
            logger.info("Committed %d updated draft(s). Failed: %d.", updated_count, failed_count)
        else:
            logger.info("No drafts were updated. Failed: %d.", failed_count)

    await client.close()
    review_service.close()


if __name__ == "__main__":
    ids = sys.argv[1:] or None
    asyncio.run(regenerate_drafts(target_ids=ids))
