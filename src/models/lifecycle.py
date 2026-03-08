from __future__ import annotations

from enum import StrEnum


class CandidateStatus(StrEnum):
    SEEN = "seen"
    SCORED = "scored"
    QUEUED = "queued"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ReviewDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class PublishJobStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    PUBLISHED = "published"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


class PublishMode(StrEnum):
    MANUAL_APPROVAL = "manual-approval"
    SEMI_AUTO = "semi-auto"


_ALLOWED_CANDIDATE_TRANSITIONS: dict[CandidateStatus, set[CandidateStatus]] = {
    CandidateStatus.SEEN: {CandidateStatus.SCORED},
    CandidateStatus.SCORED: {CandidateStatus.QUEUED, CandidateStatus.ARCHIVED},
    CandidateStatus.QUEUED: {CandidateStatus.REVIEWED, CandidateStatus.ARCHIVED, CandidateStatus.APPROVED},
    CandidateStatus.REVIEWED: {CandidateStatus.APPROVED, CandidateStatus.REJECTED, CandidateStatus.ARCHIVED},
    CandidateStatus.APPROVED: {CandidateStatus.SCHEDULED},
    CandidateStatus.SCHEDULED: {CandidateStatus.PUBLISHED},
    CandidateStatus.PUBLISHED: set(),
    CandidateStatus.REJECTED: set(),
    CandidateStatus.ARCHIVED: {CandidateStatus.QUEUED},
}


def can_transition_candidate(current: CandidateStatus, target: CandidateStatus) -> bool:
    return target in _ALLOWED_CANDIDATE_TRANSITIONS[current]


def assert_candidate_transition(current: CandidateStatus, target: CandidateStatus) -> None:
    if not can_transition_candidate(current, target):
        raise ValueError(f"Invalid candidate lifecycle transition: {current} -> {target}")
