"""Regression tests for telemetry/evidence separation at the /analyze boundary."""
import pathlib

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.evidence_adapters import adapt_behavior_evidence


client = TestClient(app)
BENIGN_VIDEO_TEXT = (
    "JioHotstar Watch TV Shows, Movies and Live Cricket. "
    "Final Highlights. Quality. Audio & Subtitles. Watch More."
)


def analyze(text=BENIGN_VIDEO_TEXT, behavior=None):
    payload = {"text": text}
    if behavior is not None:
        payload["behavior_evidence"] = {"behavior_signals": behavior}
    return client.post("/analyze", json=payload).json()


def assert_clear(result):
    assert result["risk_detected"] is False
    assert result["evidence_count"] == 0
    assert result["consumer_gate"]["decision"] == "CLEAR"
    assert result["consumer_gate"]["actionable"] is False
    assert result["explanation"]["risk_status"] == "no_strong_signal"
    assert result["explanation"]["title"] == "No strong consumer-risk signal detected"
    assert result["explanation"]["findings"][0]["type"] == "no_strong_signal"


def test_page_init_only_is_telemetry_not_evidence_or_risk():
    result = analyze(behavior=[{
        "type": "PAGE_INIT",
        "detected": True,
        "strength": "weak",
        "reason": "PAGE_INIT",
        "decision_context": "unknown",
        "journey_id": "journey-1",
        "route": "/watch",
        "event_index": 0,
    }])
    assert_clear(result)
    assert result["potential_pattern"] is None
    assert result["dark_pattern"] is None


def test_page_init_with_benign_video_text_is_clear():
    result = analyze(behavior=[{"type": "PAGE_INIT", "detected": True}])
    assert_clear(result)


def test_raw_normal_interaction_events_are_not_behavior_findings():
    result = analyze(behavior=[
        {"type": "CLICK", "detected": True, "reason": "Watch"},
        {"type": "SCROLL", "detected": True},
        {"type": "HOVER", "detected": True},
        {"type": "TAB_ACTIVE", "detected": True},
        {"type": "NAVIGATION", "detected": True},
        {"type": "INPUT_CHANGE", "detected": True},
    ])
    assert_clear(result)


def test_adapter_drops_lifecycle_events_but_keeps_semantic_behavior_findings():
    telemetry = adapt_behavior_evidence([
        {"type": "PAGE_INIT", "detected": True},
        {"type": "CLICK", "detected": True},
        {"type": "SCROLL", "detected": True},
    ])
    assert telemetry == []

    finding = adapt_behavior_evidence([{
        "type": "DIFFICULT_CANCELLATION",
        "detected": True,
        "strength": "strong",
        "reason": "Cancellation required repeated steps",
        "decision_context": "cancellation",
    }])
    assert len(finding) == 1
    assert finding[0].pattern == "obstruction"
    assert finding[0].source == "behavior"


def test_unsupported_evidence_cannot_create_generic_explanation_when_gate_is_clear():
    result = analyze(behavior=[{
        "type": "UNSUPPORTED_TELEMETRY",
        "detected": True,
        "strength": "weak",
        "reason": "A browser event was observed",
    }])
    assert result["consumer_gate"]["decision"] == "CLEAR"
    assert result["risk_detected"] is False
    assert result["explanation"]["title"] == "No strong consumer-risk signal detected"
    assert result["explanation"]["findings"][0]["type"] == "no_strong_signal"


def test_fixture_exists_for_live_like_benign_page():
    fixture = pathlib.Path(__file__).with_name("jiohotstar_regression_page.html")
    assert fixture.is_file()
