from src.services.publish_mode_service import PublishControlService


def test_publish_mode_switching_and_gating_rules() -> None:
    control = PublishControlService(initial_mode="manual-approval")

    assert not control.can_auto_publish(risk_score=1)

    control.switch_mode("semi-auto", reason="night automation")
    assert control.can_auto_publish(risk_score=1)
    assert not control.can_auto_publish(risk_score=3)

    control.pause()
    assert not control.can_publish_anything()
