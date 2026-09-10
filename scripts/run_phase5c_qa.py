"""scripts/run_phase5c_qa.py
Comprehensive Phase 5C QA, Robustness, and Model Behavior Evaluation Script.
Executes all Level 1 - Level 8 test batteries and generates evaluation statistics.
"""
import csv
import json
import os
import pathlib
import sys
import time
import numpy as np

# Ensure backend can be imported
ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend import model_loader, preprocessing
from fastapi.testclient import TestClient
from backend.main import app

# Reconfigure stdout to utf-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

client = TestClient(app)

def run_qa_evaluation():
    print("=" * 70)
    print("CLAUSEGUARD PHASE 5C — QA, ROBUSTNESS & BEHAVIOR EVALUATION")
    print("=" * 70)

    # 1. Verify Model Initialization
    model = model_loader.load_model()
    assert model is not None, "Model failed to load"
    print(f"[STATUS] Model loaded successfully: {type(model)}")

    # 2. Evaluate Real-World Test Cases (tests/real_world_test_cases.csv)
    rw_path = ROOT_DIR / "tests" / "real_world_test_cases.csv"
    assert rw_path.is_file(), "real_world_test_cases.csv not found"

    rw_results = []
    with open(rw_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row["text_sample"]
            processed = preprocessing.preprocess(text)
            pred, conf = model_loader.predict(processed)
            row["model_prediction"] = pred
            row["confidence"] = conf
            expected = row["expected_label"]
            if expected in ("0", "not_dark_pattern"):
                row["ground_truth"] = 0
            elif expected in ("1", "potential_dark_pattern"):
                row["ground_truth"] = 1
            else:
                row["ground_truth"] = None
            rw_results.append(row)

    # Compute metrics on rows with established ground truth
    eval_rows = [r for r in rw_results if r["ground_truth"] is not None]
    unknown_rows = [r for r in rw_results if r["ground_truth"] is None]
    requires_ctx_rows = [r for r in rw_results if r.get("requires_context", "").lower() == "true"]

    tp = sum(1 for r in eval_rows if r["ground_truth"] == 1 and r["model_prediction"] == 1)
    tn = sum(1 for r in eval_rows if r["ground_truth"] == 0 and r["model_prediction"] == 0)
    fp = sum(1 for r in eval_rows if r["ground_truth"] == 0 and r["model_prediction"] == 1)
    fn = sum(1 for r in eval_rows if r["ground_truth"] == 1 and r["model_prediction"] == 0)

    total_eval = len(eval_rows)
    accuracy = (tp + tn) / total_eval if total_eval > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n[REAL-WORLD QUALITY METRICS] (Evaluated on {total_eval} annotated cases):")
    print(f"  Accuracy:  {accuracy * 100:.1f}%")
    print(f"  Precision: {precision * 100:.1f}%")
    print(f"  Recall:    {recall * 100:.1f}%")
    print(f"  F1-Score:  {f1:.3f}")
    print(f"  True Positives (TP):  {tp}")
    print(f"  True Negatives (TN):  {tn}")
    print(f"  False Positives (FP): {fp}")
    print(f"  False Negatives (FN): {fn}")
    print(f"  Unknown / Ambiguous:  {len(unknown_rows)}")
    print(f"  Requires DOM Context: {len(requires_ctx_rows)}")

    # Category Breakdown
    print("\n[DOMAIN / PAGE CATEGORY BREAKDOWN]:")
    categories = sorted(set(r["page_type"] for r in rw_results))
    for cat in categories:
        cat_rows = [r for r in eval_rows if r["page_type"] == cat]
        if cat_rows:
            cat_correct = sum(1 for r in cat_rows if r["ground_truth"] == r["model_prediction"])
            cat_acc = (cat_correct / len(cat_rows)) * 100
            print(f"  {cat:<22}: {cat_correct}/{len(cat_rows)} correct ({cat_acc:.1f}%)")
        else:
            cat_all = [r for r in rw_results if r["page_type"] == cat]
            print(f"  {cat:<22}: 0/{len(cat_all)} ground truth established (context-dependent)")

    # 3. Evaluate Hard-Negative Regression Suite
    hn_path = ROOT_DIR / "tests" / "hard_negative_regression.csv"
    hn_results = []
    hn_fp_count = 0
    with open(hn_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row["text"]
            processed = preprocessing.preprocess(text)
            pred, conf = model_loader.predict(processed)
            row["model_prediction"] = pred
            row["confidence"] = conf
            if pred != 0:
                hn_fp_count += 1
            hn_results.append(row)

    print(f"\n[HARD NEGATIVE EVALUATION] ({len(hn_results)} cases containing dark-pattern keywords):")
    print(f"  Correctly classified as Not Dark Pattern: {len(hn_results) - hn_fp_count}/{len(hn_results)}")
    if hn_fp_count > 0:
        print(f"  False Positives Detected: {hn_fp_count}")
        for r in hn_results:
            if r["model_prediction"] != 0:
                print(f"    [FP] ID: {r['test_id']} ({r['category']}) -> '{r['text']}' (Conf: {r['confidence']:.3f})")
    else:
        print("  Zero False Positives in Hard Negative Suite! Excellent resistance to keyword-matching bias.")

    # 4. Evaluate Adversarial and Linguistic Cases (Negation, Unicode, Currencies, Numbers)
    adv_path = ROOT_DIR / "tests" / "adversarial_cases.csv"
    adv_results = []
    negation_failures = []
    currency_results = []
    short_input_results = []

    with open(adv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row["variant_text"]
            processed = preprocessing.preprocess(text)
            pred, conf = model_loader.predict(processed)
            row["prediction"] = pred
            row["confidence"] = conf
            adv_results.append(row)

            # Analyze specific test types
            if row["test_type"] == "negation":
                # Check if negated sentence was falsely predicted as dark pattern
                if "not" in text.lower() and pred == 1:
                    negation_failures.append(row)
            elif row["test_type"] == "currency":
                currency_results.append(row)
            elif row["test_type"] == "short_input":
                short_input_results.append(row)

    print(f"\n[ADVERSARIAL & LINGUISTIC EVALUATION] ({len(adv_results)} cases):")
    print(f"  Negation Failures: {len(negation_failures)}")
    if negation_failures:
        for nf in negation_failures:
            print(f"    [NEGATION_FAILURE] '{nf['variant_text']}' -> Pred: {nf['prediction']} (Conf: {nf['confidence']:.3f})")
    else:
        print("  All negated statements correctly identified.")

    print(f"  Currency Symbol Tests (₹, $, €, £):")
    for cr in currency_results:
        print(f"    '{cr['variant_text']}' -> Pred: {cr['prediction']} (Conf: {cr['confidence']:.3f})")

    print(f"  Short Input Robustness:")
    for sr in short_input_results:
        print(f"    '{sr['variant_text']}' -> Pred: {sr['prediction']} (Conf: {sr['confidence']:.3f})")

    # 5. Performance & Latency Benchmarks (20 repetitions)
    print("\n[PERFORMANCE BENCHMARK] (20 consecutive inference cycles):")
    sample_text = "Canceling your subscription requires contacting customer support."
    latencies_ms = []
    for _ in range(20):
        t0 = time.perf_counter()
        processed = preprocessing.preprocess(sample_text)
        model_loader.predict(processed)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    print(f"  Min latency:    {np.min(latencies_ms):.2f} ms")
    print(f"  Max latency:    {np.max(latencies_ms):.2f} ms")
    print(f"  Mean latency:   {np.mean(latencies_ms):.2f} ms")
    print(f"  Median latency: {np.median(latencies_ms):.2f} ms")

    # 6. Payload Length Boundary Tests via FastAPI TestClient
    print("\n[PAYLOAD BOUNDARY TESTS]:")
    res_100 = client.post("/predict", json={"text": "A" * 100})
    res_1000 = client.post("/predict", json={"text": "B" * 1000})
    res_5000 = client.post("/predict", json={"text": "C" * 5000})
    res_5001 = client.post("/predict", json={"text": "D" * 5001})

    print(f"  100 chars:  HTTP {res_100.status_code} (Expected 200)")
    print(f"  1000 chars: HTTP {res_1000.status_code} (Expected 200)")
    print(f"  5000 chars: HTTP {res_5000.status_code} (Expected 200)")
    print(f"  5001 chars: HTTP {res_5001.status_code} (Expected 422 Rejection)")

    assert res_100.status_code == 200
    assert res_1000.status_code == 200
    assert res_5000.status_code == 200
    assert res_5001.status_code == 422

    print("\n" + "=" * 70)
    print("PHASE 5C QA EVALUATION COMPLETED SUCCESSFULLY")
    print("=" * 70)

if __name__ == "__main__":
    run_qa_evaluation()
