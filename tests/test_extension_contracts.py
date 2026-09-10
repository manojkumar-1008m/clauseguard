"""tests/test_extension_contracts.py
Integration and contract tests verifying Chrome extension integration with FastAPI backend.
"""
import json
import pathlib
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT_DIR / "extension"


def test_manifest_contract():
    """Verify manifest.json contains all required Phase 5B MV3 properties."""
    manifest_path = EXTENSION_DIR / "manifest.json"
    assert manifest_path.is_file(), "manifest.json must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("manifest_version") == 3
    assert set(data.get("permissions")) == {"activeTab", "scripting"}
    assert data.get("host_permissions") == ["http://127.0.0.1:8000/*"]

    cs = data.get("content_scripts", [])
    assert len(cs) > 0
    assert cs[0].get("matches") == ["http://*/*", "https://*/*"]
    assert cs[0].get("js") == ["content.js"]

    action = data.get("action", {})
    assert action.get("default_popup") == "popup.html"


def test_popup_html_elements():
    """Verify popup.html defines the required IDs and structural elements."""
    html_path = EXTENSION_DIR / "popup.html"
    assert html_path.is_file()

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    required_ids = [
        "analyzeBtn",
        "status",
        "result",
        "error",
        "icon",
        "resultTitle",
        "confidence",
        "modelVersion",
        "disclaimer",
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in html_content, f"Missing id={element_id} in popup.html"


def test_popup_js_contract_and_safety():
    """Verify popup.js contains required functions, error handling, and safe DOM manipulation."""
    js_path = EXTENSION_DIR / "popup.js"
    assert js_path.is_file()

    with open(js_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Function names and required handlers
    assert "analyzeText" in code
    assert "validateResponse" in code
    assert "setIdleState" in code
    assert "setAnalyzingState" in code
    assert "setResultState" in code
    assert "setErrorState" in code

    # Safety checks
    assert "innerHTML" not in code
    assert "eval(" not in code
    assert "new Function" not in code

    # Required copy and legal terminology
    assert "Protect your digital decisions." in code or "ClauseGuard" in code
    assert "Potential Dark Pattern Detected" in code
    assert "No Strong Dark-Pattern Signal" in code
    assert "Chrome does not allow ClauseGuard to analyze this page." in code
    assert "ClauseGuard backend is unavailable. Please start the local analysis service." in code
    assert "ClauseGuard could not reach the analysis service." in code


def test_content_js_contract():
    """Verify content.js extracts text properly and enforces the 5000 character limit."""
    content_path = EXTENSION_DIR / "content.js"
    assert content_path.is_file()

    with open(content_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "extractPageText" in code
    assert "MAX_LEN = 5000" in code
    assert "chrome.runtime.onMessage.addListener" in code
    assert "GET_TEXT" in code
    assert "innerHTML" not in code


@pytest.mark.parametrize(
    "text,expected_pred,expected_label",
    [
        (
            "You can cancel your subscription at any time from Account Settings.",
            0,
            "not_dark_pattern",
        ),
        (
            "Canceling your subscription requires contacting customer support.",
            1,
            "potential_dark_pattern",
        ),
        (
            "The complete price including all mandatory fees is shown before payment.",
            0,
            "not_dark_pattern",
        ),
        (
            "A mandatory service fee will be revealed after you enter your payment details.",
            1,
            "potential_dark_pattern",
        ),
    ],
)
def test_backend_end_to_end_examples(text, expected_pred, expected_label):
    """Test the 4 required end-to-end classification examples via FastAPI client."""
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200
    data = response.json()

    assert data["prediction"] == expected_pred
    assert data["label"] == expected_label
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["model_version"] in ("clauseguard-text-v1", "clauseguard-text-v2", "clauseguard-text-v3")
    assert isinstance(data["requires_context"], bool)
