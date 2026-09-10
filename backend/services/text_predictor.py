"""backend/services/text_predictor.py
Service-layer abstraction for ClauseGuard Text Predictor.
Orchestrates preprocessing, model inference, pattern mapping,
and consumer consequence generation.
"""
from __future__ import annotations

import logging
from typing import Optional

from .. import model_loader, preprocessing, schemas
from . import consequence_engine, pattern_mapper

_logger = logging.getLogger("clauseguard_backend.text_predictor")


class ModelUnavailableError(Exception):
    """Raised when the prediction model is not available or fails to load."""
    pass


class PredictionExecutionError(Exception):
    """Raised when prediction execution fails."""
    pass


class TextPredictor:
    """Service interface orchestrating the text prediction workflow."""

    def __init__(
        self,
        loader=model_loader,
        preproc=preprocessing,
        mapper=pattern_mapper,
        engine=consequence_engine,
    ):
        self.loader = loader
        self.preproc = preproc
        self.mapper = mapper
        self.engine = engine

    def predict(self, text: str) -> schemas.PredictResponse:
        """Run complete text prediction workflow on the input text.

        Orchestration flow:
            text
             ↓
            preprocessing
             ↓
            model inference (V3)
             ↓
            context guard check
             ↓
            pattern_mapper & contradiction audit
             ↓
            evidence extraction
             ↓
            consequence_engine
             ↓
            PredictResponse
        """
        # 1. Ensure model is loaded
        if not self.loader.is_model_loaded():
            try:
                self.loader.load_model()
            except Exception as exc:
                _logger.exception("Failed to load model on predict request: %s", exc)
                raise ModelUnavailableError("Model service unavailable") from exc

        # 2. Apply preprocessing expected by the model
        processed = self.preproc.preprocess(text)

        # 3. Model inference
        try:
            pred, conf = self.loader.predict(processed)
        except Exception as exc:
            _logger.exception("Prediction failure: %s", exc)
            raise PredictionExecutionError("Prediction execution failed") from exc

        # 4. Context guard check
        req_context = self.loader.check_requires_context(text, conf)

        # 5. Deterministic pattern mapping and contradiction audit
        pattern_cat, evidence, is_benign_override = self.mapper.map_pattern(
            text=text,
            model_pred=pred,
            confidence=conf,
            requires_context=req_context,
        )

        if is_benign_override:
            pred = 0
            conf = min(conf, 0.15) if conf is not None else 0.10
            pattern_cat = None
            evidence = None
        elif pattern_cat:
            pred = 1
            conf = max(conf, 0.75) if conf is not None else 0.80

        # For short text with no specific pattern requiring context:
        if req_context and len(text.strip()) <= 80 and not pattern_cat:
            evidence = text.strip()
            pattern_cat = None

        # 6. Consumer consequence generation
        consequence = self.engine.generate_consequence(
            pattern_category=pattern_cat,
            evidence=evidence,
        )

        label = "potential_dark_pattern" if pred == 1 else "not_dark_pattern"

        _logger.info(
            "Prediction result: pred=%d, conf=%.2f, pattern=%s, requires_context=%s",
            pred,
            conf if conf is not None else 0.0,
            pattern_cat,
            req_context,
        )

        return schemas.PredictResponse(
            prediction=pred,
            label=label,
            confidence=conf,
            model_version=self.loader.get_model_version(),
            requires_context=req_context,
            pattern_category=pattern_cat,
            evidence=evidence,
            consumer_consequence=consequence,
        )
