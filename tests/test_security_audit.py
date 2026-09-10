"""tests/test_security_audit.py
Security regression test suite for ClauseGuard Chrome Extension and FastAPI Backend.
Validates the 10 requirements defined in Phase 5A security audit.
"""
import json
import os
import pathlib
import re
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT_DIR / "extension" / "manifest.json"
POPUP_JS_PATH = ROOT_DIR / "extension" / "popup.js"
MAIN_PY_PATH = ROOT_DIR / "backend" / "main.py"


def test_1_no_all_urls_in_manifest():
    """Requirement 1: No <all_urls> unless strictly justified."""
    assert MANIFEST_PATH.is_file(), "manifest.json must exist"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Check permissions, host_permissions, and content_scripts
    permissions = manifest.get("permissions", [])
    assert "<all_urls>" not in permissions, "<all_urls> found in permissions"

    host_perms = manifest.get("host_permissions", [])
    assert "<all_urls>" not in host_perms, "<all_urls> found in host_permissions"

    for cs in manifest.get("content_scripts", []):
        matches = cs.get("matches", [])
        assert "<all_urls>" not in matches, "<all_urls> found in content_scripts.matches"


def test_2_no_unnecessary_permissions():
    """Requirement 2: No unneeded permissions like tabs, cookies, webRequest, history, etc."""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    forbidden_permissions = {
        "tabs",
        "webRequest",
        "webNavigation",
        "cookies",
        "storage",
        "history",
        "debugger",
        "downloads",
        "bookmarks",
        "management",
        "notifications",
    }
    permissions = set(manifest.get("permissions", []))
    violating = permissions.intersection(forbidden_permissions)
    assert not violating, f"Unnecessary permissions declared: {violating}"
    # Minimal required baseline
    assert permissions == {"activeTab", "scripting"}, f"Expected permissions to be {{'activeTab', 'scripting'}}, got {permissions}"


def test_3_no_wildcard_cors():
    """Requirement 3: No wildcard allow_origins=['*'] in CORS configuration."""
    with open(MAIN_PY_PATH, "r", encoding="utf-8") as f:
        code = f.read()

    assert 'allow_origins=["*"]' not in code.replace(" ", ""), "Wildcard allow_origins=['*'] found in main.py"
    assert "allow_origins=['*']" not in code.replace(" ", ""), "Wildcard allow_origins=['*'] found in main.py"


def test_4_empty_input_rejected():
    """Requirement 4: Empty and whitespace-only input must be rejected with 422."""
    res_empty = client.post("/predict", json={"text": ""})
    assert res_empty.status_code == 422, f"Expected 422, got {res_empty.status_code}"

    res_spaces = client.post("/predict", json={"text": "   \t\n   "})
    assert res_spaces.status_code == 422, f"Expected 422, got {res_spaces.status_code}"


def test_5_oversized_input_rejected():
    """Requirement 5: Oversized input exceeding max length must be rejected with 422."""
    oversized = "A" * 5001
    res = client.post("/predict", json={"text": oversized})
    assert res.status_code == 422, f"Expected 422 for oversized text, got {res.status_code}"


def test_6_malformed_request_rejected():
    """Requirement 6: Malformed JSON or non-string text types rejected with 422."""
    res_missing = client.post("/predict", json={})
    assert res_missing.status_code == 422

    res_type = client.post("/predict", json={"text": 12345})
    assert res_type.status_code == 422

    res_nested = client.post("/predict", json={"text": ["nested", "data"]})
    assert res_nested.status_code == 422


def test_7_exception_does_not_leak_traceback(monkeypatch):
    """Requirement 7: Backend internal error does not expose stack trace or filesystem paths."""
    from backend import model_loader

    def fake_predict(text):
        raise RuntimeError("C:/Secret/Internal/Path/critical_failure.py: line 42")

    monkeypatch.setattr(model_loader, "predict", fake_predict)
    # Ensure model loaded returns True so it hits predict
    monkeypatch.setattr(model_loader, "is_model_loaded", lambda: True)

    res = client.post("/predict", json={"text": "Canceling your subscription requires calling support."})
    assert res.status_code == 500
    detail = res.json().get("detail", "")
    assert "C:/Secret/Internal/Path" not in detail, "Internal path leaked in error detail"
    assert "Traceback" not in detail, "Traceback leaked in error detail"
    assert "line 42" not in detail, "Code line numbers leaked in error detail"
    assert detail == "Prediction execution failed"


def test_8_extension_handles_backend_failure_safely():
    """Requirement 8: popup.js has explicit error presentation handling."""
    with open(POPUP_JS_PATH, "r", encoding="utf-8") as f:
        popup_code = f.read()

    assert "showError" in popup_code, "popup.js must implement showError handler"
    assert "errorDiv.textContent" in popup_code, "popup.js must set error text via textContent"


def test_9_untrusted_text_rendered_safely():
    """Requirement 9: popup.js must render all dynamic text safely without innerHTML or eval."""
    with open(POPUP_JS_PATH, "r", encoding="utf-8") as f:
        popup_code = f.read()

    assert "innerHTML" not in popup_code, "Unsafe innerHTML found in popup.js"
    assert "eval(" not in popup_code, "eval() found in popup.js"
    assert "document.write" not in popup_code, "document.write found in popup.js"
    assert "new Function" not in popup_code, "new Function found in popup.js"


def test_10_no_secrets_in_source_files():
    """Requirement 10: No secret API keys, tokens, or credentials checked into source tree."""
    gitignore_path = ROOT_DIR / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore must exist"
    with open(gitignore_path, "r", encoding="utf-8") as f:
        gitignore_content = f.read()
    assert ".env" in gitignore_content, ".env must be in .gitignore"

    secret_pattern = re.compile(
        r"""(?i)(?:api_key|secret_key|private_key|auth_token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"""
    )
    for root, _, files in os.walk(ROOT_DIR):
        if ".git" in root or ".venv" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith((".py", ".js", ".json", ".html", ".css", ".md")):
                path = pathlib.Path(root) / file
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = secret_pattern.findall(content)
                    assert not matches, f"Potential secret found in {path}: {matches}"
