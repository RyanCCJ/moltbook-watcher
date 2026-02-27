from __future__ import annotations

from src.services.logging_service import get_logger

logger = get_logger(__name__)


class AuditService:
    def log_review_action(self, *, review_item_id: str, decision: str, reviewed_by: str | None) -> None:
        logger.info(
            "review_action",
            review_item_id=review_item_id,
            decision=decision,
            reviewed_by=reviewed_by,
        )

    def log_mode_change(self, *, from_mode: str, to_mode: str, reason: str | None) -> None:
        logger.info(
            "publish_mode_changed",
            from_mode=from_mode,
            to_mode=to_mode,
            reason=reason,
        )
