"""backend/model_loader.py
Singleton pattern for loading the ClauseGuard model once at startup.
"""
import pathlib
import joblib
import logging

# Compatibility shim for notebook‑local preprocessing used during model training
def production_preprocessor(text: str) -> str:
    """Minimal preprocessing: strip and collapse whitespace."""
    import re
    cleaned = text.strip()
    return re.sub(r"\\s+", " ", cleaned)
from typing import Any, Tuple

_logger = logging.getLogger(__name__)

_MODEL_DIR = pathlib.Path(__file__).resolve().parents[1] / "model"
_MODEL_V3_PATH = _MODEL_DIR / "clauseguard_model_v3.joblib"
_MODEL_V2_PATH = _MODEL_DIR / "clauseguard_model_v2.joblib"
_MODEL_V1_PATH = _MODEL_DIR / "clauseguard_model_v1.joblib"

_MODEL_PATH = _MODEL_V2_PATH if _MODEL_V2_PATH.is_file() else _MODEL_V1_PATH
_model_version: str = "clauseguard-text-v3"

_model: Any = None

def get_model_version() -> str:
    return _model_version

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
    return int(pred), conf

