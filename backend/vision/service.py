"""Backend Vision evidence producer using the trained MobileNetV3 detector."""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional

from .vision_module import VisionDetector


DEFAULT_CHECKPOINT_PATH = Path(__file__).with_name("mobilenetv3_v3_best.pth")


class VisionService:
    """Run trained Vision inference and format results for Evidence Fusion."""

    def __init__(self, checkpoint_path: Optional[Path] = None, device: Optional[str] = None):
        self.checkpoint_path = Path(checkpoint_path or DEFAULT_CHECKPOINT_PATH)
        self.detector = VisionDetector(str(self.checkpoint_path), device=device)

    @property
    def model(self) -> str:
        return str(self.detector.checkpoint["model_name"])

    @property
    def version(self) -> str:
        return str(self.detector.checkpoint["version"])

    def predict_path(self, image_path: str | Path, frame_id: Optional[str] = None) -> Dict[str, Any]:
        result = self.detector.predict(str(image_path))
        return self._with_image_evidence(result, frame_id=frame_id)

    def predict_bytes(self, image_bytes: bytes, suffix: str = ".png", frame_id: Optional[str] = None) -> Dict[str, Any]:
        with NamedTemporaryFile(suffix=suffix, delete=False) as image_file:
            image_file.write(image_bytes)
            image_path = image_file.name
        try:
            return self.predict_path(image_path, frame_id=frame_id)
        finally:
            Path(image_path).unlink(missing_ok=True)

    def _with_image_evidence(self, result: Dict[str, Any], frame_id: Optional[str]) -> Dict[str, Any]:
        image_evidence = []
        for label, prediction in result["predictions"].items():
            probability = float(prediction["probability"])
            detected = bool(prediction["detected"])
            image_evidence.append(
                {
                    "signal_type": label,
                    "type": label,
                    "detected": detected,
                    "model_confidence": probability,
                    "confidence": probability,
                    "description": f"Vision model detected {label}." if detected else f"Vision model did not detect {label}.",
                    "frame_id": frame_id,
                    "provenance": f"vision:{result['model']}:{result['version']}",
                    "metadata": {
                        "model": result["model"],
                        "model_version": result["version"],
                        "threshold": float(prediction["threshold"]),
                        "confidence_percent": float(prediction["confidence_percent"]),
                    },
                }
            )

        return {
            **result,
            "image_evidence": image_evidence,
            "frame_id": frame_id,
        }
