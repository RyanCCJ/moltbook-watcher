from src.services.dedup_service import DedupService


def test_fingerprint_is_stable_for_semantically_equivalent_text() -> None:
    service = DedupService()
    fingerprint_a = service.build_fingerprint("AI agents should cite original posts for attribution")
    fingerprint_b = service.build_fingerprint("Attribution for original posts should be cited by AI agents")

    assert fingerprint_a == fingerprint_b


def test_should_filter_near_duplicates_above_threshold() -> None:
    service = DedupService(similarity_threshold=0.75)
    existing = ["AI curation needs reliable lifecycle transitions for content operations"]

    assert service.should_filter("AI curation needs reliable lifecycle transition for operations", existing)
    assert not service.should_filter("Threads API retries should notify operators", existing)
