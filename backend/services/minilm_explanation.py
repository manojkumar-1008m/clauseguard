"""Optional MiniLM semantic retrieval for evidence-grounded explanations.

MiniLM ranks already-verified evidence. It never generates user-facing facts and
never receives authority over the canonical risk or consumer gate.
"""
from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Any, Dict, List, Optional

from ..schemas.explanation import ExplanationResponse
from ..schemas.explanation_context import ExplanationContext

logger = logging.getLogger("clauseguard_backend.minilm_explanation")


class MiniLMExplanationLayer:
    """Lazy, cached MiniLM evidence ranker with a deterministic fallback."""

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: Optional[str] = None, backend: Any = None):
        self.model_name = model_name or os.getenv("CLAUSEGUARD_MINILM_MODEL", self.DEFAULT_MODEL)
        self._backend = backend
        self._load_lock = Lock()
        self._load_ms: Optional[float] = None
        self._load_error: Optional[str] = None

    def enhance(
        self, explanation: ExplanationResponse, context: Optional[ExplanationContext]
    ) -> ExplanationResponse:
        """Attach semantic evidence ranking without changing explanation facts."""
        started = time.perf_counter()
        metadata: Dict[str, Any] = dict(explanation.metadata or {})
        semantic: Dict[str, Any] = {
            "model": self.model_name,
            "task": "semantic_evidence_ranking",
            "device": "cpu",
            "model_used": False,
        }

        if context is None or not context.evidence_descriptions:
            semantic["status"] = "insufficient_context"
            semantic["reason"] = "No verified evidence descriptions were supplied."
            return self._with_metadata(explanation, metadata, semantic)

        if os.getenv("CLAUSEGUARD_MINILM_ENABLED", "1") != "1":
            semantic["status"] = "disabled"
            semantic["reason"] = "MiniLM disabled by configuration"
            return self._with_metadata(explanation, metadata, semantic)

        if context.requires_context:
            semantic["status"] = "insufficient_context"
            semantic["reason"] = "Upstream analysis marked additional context as required."
            return self._with_metadata(explanation, metadata, semantic)

        try:
            backend = self._get_backend()
            query = self._query(context)
            scores = backend.similarity(query, context.evidence_descriptions)
            order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
            semantic.update(
                {
                    "status": "ok",
                    "model_used": True,
                    "ranked_evidence_ids": [context.evidence_ids[i] for i in order if i < len(context.evidence_ids)],
                    "scores": [round(float(scores[i]), 6) for i in order],
                    "inference_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("MiniLM unavailable; using deterministic explanation fallback", exc_info=True)
            semantic.update(
                {
                    "status": "fallback",
                    "reason": "MiniLM unavailable",
                    "inference_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )

        semantic["load_ms"] = self._load_ms
        semantic["memory_mb"] = self._memory_mb()
        return self._with_metadata(explanation, metadata, semantic)

    def _get_backend(self) -> Any:
        if self._backend is not None:
            return self._backend
        with self._load_lock:
            if self._backend is not None:
                return self._backend
            started = time.perf_counter()
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer

                local_only = os.getenv("CLAUSEGUARD_MINILM_LOCAL_ONLY", "1") == "1"
                tokenizer = AutoTokenizer.from_pretrained(self.model_name, local_files_only=local_only)
                model = AutoModel.from_pretrained(self.model_name, local_files_only=local_only)
                model.eval()
                self._backend = _TransformersEmbeddingBackend(tokenizer, model, torch)
                self._load_ms = round((time.perf_counter() - started) * 1000, 3)
                return self._backend
            except Exception as exc:
                self._load_ms = round((time.perf_counter() - started) * 1000, 3)
                self._load_error = str(exc)
                raise

    @staticmethod
    def _query(context: ExplanationContext) -> str:
        fields = [context.pattern, context.consequence, context.recommended_action, context.decision_context]
        return " ".join(value for value in fields if value)

    @staticmethod
    def _memory_mb() -> Optional[float]:
        try:
            import psutil

            return round(psutil.Process().memory_info().rss / (1024 * 1024), 2)
        except Exception:
            return None

    @staticmethod
    def _with_metadata(
        explanation: ExplanationResponse, metadata: Dict[str, Any], semantic: Dict[str, Any]
    ) -> ExplanationResponse:
        metadata["semantic_layer"] = semantic
        return explanation.model_copy(update={"metadata": metadata})


class _TransformersEmbeddingBackend:
    """Mean-pooled, normalized CPU embeddings used only for similarity ranking."""

    def __init__(self, tokenizer: Any, model: Any, torch_module: Any):
        self.tokenizer = tokenizer
        self.model = model
        self.torch = torch_module

    def similarity(self, query: str, evidence: List[str]) -> List[float]:
        texts = [query, *evidence]
        encoded = self.tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        with self.torch.no_grad():
            output = self.model(**encoded)
        mask = encoded["attention_mask"].unsqueeze(-1).float()
        pooled = (output.last_hidden_state * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
        normalized = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
        return self.torch.matmul(normalized[1:], normalized[0]).tolist()