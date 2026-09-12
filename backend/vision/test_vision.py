"""Minimal real-image validation for the trained Vision evidence producer."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from backend.services.evidence_adapters import adapt_image_evidence
from backend.vision.service import VisionService


EXPECTED_LABEL_COUNT = 10


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path, help="Path to a real screenshot/image")
    args = parser.parse_args()

    service = VisionService()
    result = service.predict_path(args.image, frame_id="validation-frame-001")

    assert result["model"] == "MobileNetV3-Small"
    assert result["version"] == "V3"
    assert len(result["predictions"]) == EXPECTED_LABEL_COUNT
    assert all(math.isfinite(float(item["probability"])) for item in result["predictions"].values())

    evidence = adapt_image_evidence(result["image_evidence"])
    assert len(evidence) == EXPECTED_LABEL_COUNT
    assert all(item.source == "image" for item in evidence)
    assert all(item.frame_id == "validation-frame-001" for item in evidence)
    assert all(item.model_confidence is not None for item in evidence)

    print("model:", result["model"])
    print("version:", result["version"])
    for label, prediction in result["predictions"].items():
        print(f"{label}: probability={prediction['probability']:.6f} detected={prediction['detected']}")
    print("image_evidence_items:", len(evidence))
    print("VISION_VALIDATION_OK")


if __name__ == "__main__":
    main()
