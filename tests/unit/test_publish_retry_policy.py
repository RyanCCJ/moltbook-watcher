from src.services.publish_retry_policy import PublishRetryPolicy


def test_retry_policy_terminal_failure_after_max_attempts() -> None:
    policy = PublishRetryPolicy(max_attempts=3, base_delay_seconds=30)

    assert policy.should_retry(attempt_count=0)
    assert policy.should_retry(attempt_count=1)
    assert policy.should_retry(attempt_count=2)
    assert not policy.should_retry(attempt_count=3)


def test_retry_policy_backoff_increases() -> None:
    policy = PublishRetryPolicy(max_attempts=3, base_delay_seconds=30)

    assert policy.next_delay_seconds(attempt_count=1) == 30
    assert policy.next_delay_seconds(attempt_count=2) == 60
    assert policy.next_delay_seconds(attempt_count=3) == 120
