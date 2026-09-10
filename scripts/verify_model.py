#!/usr/bin/env python

# Compatibility shim for notebook-local function
def production_preprocessor(text: str) -> str:
    """Minimal preprocessing used during training.
    Strips whitespace and collapses multiple spaces.
    """
    import re
    cleaned = text.strip()
    return re.sub(r"\s+", " ", cleaned)

"""scripts/verify_model.py
Verification script for the ClauseGuard model.
It performs the following steps:
1. Ensures the model file exists.
2. Loads the model with joblib, catching and reporting any errors.
3. Prints the exact Python type of the loaded object.
4. Determines whether the object is a scikit‑learn Pipeline, a classifier,
   a calibrated classifier, or something else.
5. Detects common notebook‑local dependencies by inspecting the exception
   message (e.g., references to "__main__" or a custom function name).
6. Runs two sanity‑check predictions and prints the input, prediction,
   and confidence (if available).
7. Exits with status 0 on success, non‑zero on failure.
"""
import sys
import pathlib
import joblib
import traceback
from typing import Any, Tuple

MODEL_PATH = pathlib.Path(__file__).resolve().parents[1] / "model" / "clauseguard_model_v1.joblib"

def main() -> int:
    # 1. Check existence
    if not MODEL_PATH.is_file():
        print(f"[ERROR] Model file not found at {MODEL_PATH}")
        return 1
    print(f"[INFO] Found model file: {MODEL_PATH}")

    # 2. Load model safely
    try:
        model = joblib.load(MODEL_PATH)
    except Exception as e:
        tb = traceback.format_exc()
        print("[ERROR] Failed to load model:")
        print(tb)
        # Classify common dependency problems
        if "__main__" in str(e) or "production_preprocessor" in str(e):
            classification = "B. Notebook‑local function/class dependency"
        elif "module" in str(e) and "sklearn" in str(e):
            classification = "D. scikit‑learn version incompatibility"
        elif "ImportError" in str(e):
            classification = "A. Missing dependency"
        else:
            classification = "F. Other"
        print(f"[CLASSIFICATION] {classification}")
        return 2

    # 3. Print model type
    print(f"[INFO] Loaded model type: {type(model)}")

    # 4. Inspect model kind
    is_pipeline = False
    is_classifier = False
    is_calibrated = False

    try:
        from sklearn.pipeline import Pipeline
        is_pipeline = isinstance(model, Pipeline)
    except Exception:
        pass
    try:
        # Any estimator with a predict method qualifies as a classifier for our use‑case
        is_classifier = hasattr(model, "predict")
    except Exception:
        pass
    try:
        from sklearn.calibration import CalibratedClassifierCV
        is_calibrated = isinstance(model, CalibratedClassifierCV)
    except Exception:
        pass

    print("[INFO] Model characteristics:")
    print(f"  - sklearn Pipeline: {is_pipeline}")
    print(f"  - classifier with predict(): {is_classifier}")
    print(f"  - calibrated classifier: {is_calibrated}")

    # 5. Define a small helper to run prediction
    def run_prediction(text: str) -> Tuple[int, Any]:
        pred = model.predict([text])[0]
        conf = None
        if hasattr(model, "predict_proba"):
            try:
                prob = model.predict_proba([text])[0]
                # Binary classifier: probability of class 1
                if len(prob) > 1:
                    conf = float(prob[1])
                else:
                    conf = float(prob[0])
            except Exception:
                conf = None
        return int(pred), conf

    # 6. Run sanity‑check predictions
    test_cases = [
        "Canceling your subscription requires contacting customer support.",
        "The total price including all mandatory fees is shown before payment.",
    ]
    for txt in test_cases:
        try:
            pred, conf = run_prediction(txt)
            print("[TEST] Input:", txt)
            print("       Prediction:", pred)
            print("       Confidence:", conf)
            if pred not in (0, 1):
                print(f"[ERROR] Unexpected prediction value {pred}; expected 0 or 1.")
                return 3
        except Exception as e:
            print("[ERROR] Prediction failed for input:", txt)
            print(traceback.format_exc())
            return 4

    print("[SUCCESS] Model verification completed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
