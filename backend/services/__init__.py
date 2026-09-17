"""backend/services/__init__.py
Explainability, pattern detection, and analyzer services for ClauseGuard.
"""
from .evidence_fusion import EvidenceFusionEngine
from .explanation_engine import ConsumerExplanationEngine
from .consumer_risk_gate import ConsumerRiskGate
from .minilm_explanation import MiniLMExplanationLayer
from .ask_clauseguard import AskClauseGuardService
from .price_analyzer import PriceAnalyzer
from .text_predictor import (
    TextPredictor,
    ModelUnavailableError,
    PredictionExecutionError,
)

__all__ = [
    "TextPredictor",
    "ModelUnavailableError",
    "PredictionExecutionError",
    "PriceAnalyzer",
    "EvidenceFusionEngine",
    "ConsumerExplanationEngine",
    "ConsumerRiskGate",
    "MiniLMExplanationLayer",
    "AskClauseGuardService",
]


