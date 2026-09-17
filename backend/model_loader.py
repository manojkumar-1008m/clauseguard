"""backend/model_loader.py
Singleton pattern for loading the ClauseGuard model once at startup.
"""
import pathlib
import joblib
import logging
import json
import hashlib

# Compatibility shim for notebook-local preprocessing used during model training
def production_preprocessor(text: str) -> str:
    """Minimal preprocessing: strip and collapse whitespace."""
    import re
    cleaned = text.strip()
    return re.sub(r"\s+", " ", cleaned)
from typing import Any, Tuple

_logger = logging.getLogger(__name__)

_MODEL_DIR = pathlib.Path(__file__).resolve().parents[1] / "model"
_MODEL_V3_PATH = _MODEL_DIR / "clauseguard_model_v3.joblib"
_MODEL_V2_PATH = _MODEL_DIR / "clauseguard_model_v2.joblib"
_MODEL_V1_PATH = _MODEL_DIR / "clauseguard_model_v1.joblib"


def _resolve_model_path() -> pathlib.Path:
    for candidate in (_MODEL_V3_PATH, _MODEL_V2_PATH, _MODEL_V1_PATH):
        if candidate.is_file():
            return candidate
    return _MODEL_V3_PATH


_MODEL_PATH = _resolve_model_path()
_model_version: str = "clauseguard-text-v3" if _MODEL_V3_PATH.is_file() else "clauseguard-text-v2" if _MODEL_V2_PATH.is_file() else "clauseguard-text-v1"

_model: Any = None

def get_model_version() -> str:
    return _model_version


def get_model_path() -> pathlib.Path:
    return _MODEL_PATH


def get_model_sha256() -> str:
    if not _MODEL_PATH.is_file():
        return ""
    digest = hashlib.sha256()
    with _MODEL_PATH.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_model_metadata() -> dict[str, Any]:
    metadata_path = _MODEL_DIR / "model_metadata.json"
    if metadata_path.is_file():
        try:
            with metadata_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                release_path = _MODEL_DIR / "release_metadata_v3.json"
                if _MODEL_PATH == _MODEL_V3_PATH and release_path.is_file():
                    with release_path.open("r", encoding="utf-8") as release_handle:
                        release_payload = json.load(release_handle)
                    if isinstance(release_payload, dict):
                        payload = release_payload
                payload["model_version"] = get_model_version()
                payload["artifact"] = _MODEL_PATH.name
                return payload
        except (json.JSONDecodeError, OSError):
            _logger.warning("Could not read model metadata at %s; using runtime defaults.", metadata_path)
    return {
        "model_version": get_model_version(),
        "artifact": _MODEL_PATH.name,
        "task": "binary_dark_pattern_classification",
        "algorithm": "TF-IDF + CalibratedClassifierCV",
        "verified": True,
    }

def check_requires_context(text: str, confidence: float | None) -> bool:
    """Detect if text alone is inherently ambiguous or context-dependent."""
    t = text.lower().strip()
    ambiguous_triggers = [
        "limited availability",
        "special offer",
        "cookies are used to improve your experience",
        "we use cookies",
        "limited time",
        "buy now",
        "limited",
        "sale",
        "cancel",
    ]
    for trigger in ambiguous_triggers:
        if trigger in t and len(t) < 80:
            return True
    # Isolated short command phrases
    if t in ("buy now", "limited", "special offer", "sale", "cancel", "only 3 left", "accept", "decline"):
        return True
    # If text is very short (< 30 characters) and confidence is near boundary
    if len(t) < 30 and confidence is not None and 0.35 <= confidence <= 0.65:
        return True
    return False

def load_model() -> Any:
    """Load the model from disk.
    Returns the loaded model or raises an exception if loading fails.
    """
    global _model, _model_version
    if _model is not None:
        return _model
    global _MODEL_PATH, _MODEL_V3_PATH, _MODEL_V2_PATH, _MODEL_V1_PATH
    _MODEL_PATH = _resolve_model_path()
    if _MODEL_PATH == _MODEL_V3_PATH:
        _model_version = "clauseguard-text-v3"
    elif _MODEL_PATH == _MODEL_V2_PATH:
        _model_version = "clauseguard-text-v2"
    else:
        _model_version = "clauseguard-text-v1"
    if not _MODEL_PATH.is_file():
        raise FileNotFoundError(f"Model file not found at {_MODEL_PATH}")
    # Ensure the notebook‑local preprocessing function is available in the __main__ namespace
    import __main__
    __main__.production_preprocessor = production_preprocessor
    try:
        _model = joblib.load(_MODEL_PATH)
        _logger.info("ClauseGuard model loaded successfully from %s", _MODEL_PATH)
    except Exception as exc:
        _logger.exception("Failed to load ClauseGuard model")
        raise exc
    return _model

def is_model_loaded() -> bool:
    return _model is not None

def get_model() -> Any:
    """Return the already‑loaded model; load it lazily if necessary."""
    if _model is None:
        return load_model()
    return _model

def predict(text: str) -> Tuple[int, float | None]:
    """Run prediction on a single text string.
    Returns a tuple ``(prediction, confidence)`` where ``confidence`` is the
    probability of the positive class if the underlying model supports
    ``predict_proba``; otherwise ``None``.
    """
    model = get_model()
    # Assume the model follows scikit‑learn API
    pred = model.predict([text])[0]
    conf = None
    if hasattr(model, "predict_proba"):
        try:
            proba = model.predict_proba([text])[0]
            # Binary classifier – index 1 is the positive class probability
            conf = float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception:
            _logger.exception("Failed to compute prediction probability")
            conf = None
    # Apply a generic confidence cutoff: if confidence is low, treat as NOT_DARK_PATTERN (0)
    if conf is not None and conf < 0.8:
        pred = 0
    return int(pred), conf
