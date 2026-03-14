import pytest

from src.models.lifecycle import (
    CandidateStatus,
    assert_candidate_transition,
    can_transition_candidate,
)


def test_can_transition_candidate_allows_archived_to_queued() -> None:
    assert can_transition_candidate(CandidateStatus.ARCHIVED, CandidateStatus.QUEUED) is True


def test_can_transition_candidate_allows_scored_to_archived() -> None:
    assert can_transition_candidate(CandidateStatus.SCORED, CandidateStatus.ARCHIVED) is True


def test_can_transition_candidate_allows_queued_to_approved() -> None:
    assert can_transition_candidate(CandidateStatus.QUEUED, CandidateStatus.APPROVED) is True


def test_other_transitions_from_archived_still_raise() -> None:
    with pytest.raises(ValueError, match="Invalid candidate lifecycle transition"):
        assert_candidate_transition(CandidateStatus.ARCHIVED, CandidateStatus.APPROVED)
