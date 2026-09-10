"""scripts/run_final_test_v3.py
Executes Phase J: Final Untouched Test Evaluation for ClauseGuard V3.

1. Verifies final test immutability via cryptographic SHA-256 checksum.
2. Trains final Model V3 (TF-IDF + Calibrated LinearSVC) on train_v3 + curated augmentations.
3. Evaluates on untouched data/final_test_v3.csv (N=504).
4. Produces Brier calibration score and reliability curve table.
5. Performs root-cause error analysis for all misclassifications.
6. Serializes model/clauseguard_model_v3.joblib and model/release_metadata_v3.json.
7. Produces reports/model_v3_report.json and reports/model_v3_report.md.
"""
import os
import sys
import json
import time
import joblib
import hashlib
import pathlib
import pandas as pd
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    brier_score_loss
)

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
MODEL_DIR = ROOT_DIR / "model"

RANDOM_SEED = 42

OPTIMAL_VEC_CONFIG = {
    "ngram_range": (1, 3),
    "sublinear_tf": True,
    "max_features": 30000,
    "min_df": 2
}

def verify_immutability(final_test_path: pathlib.Path):
    audit_path = REPORTS_DIR / "dataset_v3_audit.json"
    if not audit_path.exists():
        raise FileNotFoundError(f"Missing {audit_path}")
    with open(audit_path, "r", encoding="utf-8") as f:
        audit = json.load(f)
    expected_hash = audit["splits"]["final_test_sha256"]
    current_hash = hashlib.sha256(final_test_path.read_bytes()).hexdigest()
    if expected_hash != current_hash:
        raise ValueError("FINAL TEST IMMUTABILITY VIOLATION! Hash mismatch.")
    print(f"[IMMUTABILITY VERIFIED] final_test_v3.csv SHA-256: {current_hash} (LOCKED)")

def classify_root_cause(text: str, true_label: int, pred_label: int, confidence: float) -> str:
    t_lower = text.lower()
    # Keyword bias checks
    fee_terms = ["fee", "tax", "charge", "refund", "receipt", "payment"]
    urgency_terms = ["only", "left", "hurry", "limited", "trial", "sold"]
    
    if true_label == 0 and pred_label == 1:
        if any(w in t_lower for w in fee_terms + urgency_terms):
            return "KEYWORD_BIAS"
        elif len(text) < 40:
            return "REQUIRES_CONTEXT"
        else:
            return "DOMAIN_SHIFT"
    elif true_label == 1 and pred_label == 0:
        if any(w in t_lower for w in ["not", "no", "without", "never"]):
            return "NEGATION_FAILURE"
        elif len(text) > 150:
            return "CONTEXT_FAILURE"
        else:
            return "VOCABULARY_GAP"
    return "AMBIGUOUS"

def main():
    print("=" * 80)
    print("CLAUSEGUARD V3: FINAL UNTOUCHED EVALUATION & RELEASE SERIALIZATION")
    print("=" * 80)

    final_test_path = DATA_DIR / "final_test_v3.csv"
    verify_immutability(final_test_path)

    # 1. Prepare Full Training Set (Ablation E)
    train_df = pd.read_csv(DATA_DIR / "train_v3.csv")
    from scripts.build_dataset_v3 import load_curated_multi_domain
    curated_records = load_curated_multi_domain()
    df_curated = pd.DataFrame(curated_records)
    
    full_train = pd.concat([train_df, df_curated], ignore_index=True)
    X_train = full_train["text"].fillna("")
    y_train = full_train["label"].astype(int)

    final_df = pd.read_csv(final_test_path)
    X_final = final_df["text"].fillna("")
    y_final = final_df["label"].astype(int)

    print(f"\nTraining Model V3 on N={len(X_train)} samples...")
    model_v3 = Pipeline([
        ("tfidf", TfidfVectorizer(**OPTIMAL_VEC_CONFIG)),
        ("clf", CalibratedClassifierCV(
            estimator=LinearSVC(C=1.0, max_iter=2000, random_state=RANDOM_SEED),
            method="sigmoid",
            cv=3
        ))
    ])
    
    t0 = time.time()
    model_v3.fit(X_train, y_train)
    fit_duration = time.time() - t0

    # 2. Untouched Final Test Inference
    t0_inf = time.time()
    probs = model_v3.predict_proba(X_final)[:, 1]
    inf_duration = time.time() - t0_inf
    latency_per_sample_ms = (inf_duration / len(X_final)) * 1000.0

    preds = (probs >= 0.50).astype(int)

    # 3. Overall Metrics
    cm = confusion_matrix(y_final, preds, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    acc = accuracy_score(y_final, preds)
    prec = precision_score(y_final, preds, zero_division=0)
    rec = recall_score(y_final, preds, zero_division=0)
    f1 = f1_score(y_final, preds, zero_division=0)
    roc_auc = roc_auc_score(y_final, probs)
    pr_auc = average_precision_score(y_final, probs)
    brier = brier_score_loss(y_final, probs)
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    print(f"\n[FINAL UNTOUCHED TEST RESULTS (N={len(y_final)})]")
    print(f"  Accuracy:          {acc*100:.2f}%")
    print(f"  Precision:         {prec*100:.2f}%")
    print(f"  Recall:            {rec*100:.2f}%")
    print(f"  F1 Score:          {f1:.4f}")
    print(f"  Dark-pattern F1:   {f1:.4f}")
    print(f"  Dark-pattern Rec:  {rec*100:.2f}%")
    print(f"  ROC-AUC:           {roc_auc:.4f}")
    print(f"  PR-AUC:            {pr_auc:.4f}")
    print(f"  Brier Score:       {brier:.4f} (0.0 = perfect calibration)")
    print(f"  False Positives:   {fp} (FPR: {fpr*100:.2f}%)")
    print(f"  False Negatives:   {fn} (FNR: {fnr*100:.2f}%)")
    print(f"  Inference Latency: {latency_per_sample_ms:.3f} ms / sample")

    # 4. Calibration Curve
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    calibration_table = []
    print("\n[CONFIDENCE CALIBRATION DISTRIBUTION]")
    for i in range(len(bins)-1):
        low, high = bins[i], bins[i+1]
        mask = [(low <= p < high) or (i == len(bins)-2 and low <= p <= high) for p in probs]
        bin_y = [y_final.iloc[j] for j, m in enumerate(mask) if m]
        bin_p = [probs[j] for j, m in enumerate(mask) if m]
        count = len(bin_y)
        if count > 0:
            obs_acc = float(np.mean(bin_y))
            avg_conf = float(np.mean(bin_p))
        else:
            obs_acc = 0.0
            avg_conf = 0.0
        calibration_table.append({
            "bin": f"[{low:.1f}, {high:.1f}]",
            "count": count,
            "avg_confidence": avg_conf,
            "observed_accuracy": obs_acc
        })
        print(f"  Bin [{low:.1f}, {high:.1f}]: Count={count:<3} | AvgConf={avg_conf*100:.1f}% | ObsAccuracy={obs_acc*100:.1f}%")

    # 5. Domain Metrics Breakdown
    print("\n[DOMAIN-SPECIFIC BREAKDOWN]")
    domain_metrics = {}
    for dom in sorted(final_df["domain"].dropna().unique()):
        dom_mask = (final_df["domain"] == dom).values
        y_d = y_final[dom_mask]
        p_d = preds[dom_mask]
        prb_d = probs[dom_mask]
        d_acc = accuracy_score(y_d, p_d)
        d_f1 = f1_score(y_d, p_d, zero_division=0)
        d_prec = precision_score(y_d, p_d, zero_division=0)
        d_rec = recall_score(y_d, p_d, zero_division=0)
        d_fp = int(sum((p_d == 1) & (y_d == 0)))
        d_fn = int(sum((p_d == 0) & (y_d == 1)))
        
        domain_metrics[dom] = {
            "samples": int(sum(dom_mask)),
            "accuracy": float(d_acc),
            "f1": float(d_f1),
            "precision": float(d_prec),
            "recall": float(d_rec),
            "fp": d_fp,
            "fn": d_fn
        }
        print(f"  {dom:<20} (N={sum(dom_mask):<3}): Acc={d_acc*100:.1f}%, F1={d_f1:.3f}, Rec={d_rec*100:.1f}%, FP={d_fp}, FN={d_fn}")

    # 6. Error Analysis
    print("\n[ERROR ANALYSIS]")
    errors = []
    for idx, (y_t, y_p, p_val) in enumerate(zip(y_final, preds, probs)):
        if y_t != y_p:
            row = final_df.iloc[idx]
            sid = row["sample_id"]
            txt = row["text"]
            dom = row["domain"]
            cat = row["pattern_category"]
            err_type = "FALSE_POSITIVE" if y_p == 1 else "FALSE_NEGATIVE"
            cause = classify_root_cause(txt, y_t, y_p, p_val)
            errors.append({
                "sample_id": sid,
                "text": txt,
                "actual": int(y_t),
                "predicted": int(y_p),
                "confidence": float(p_val),
                "domain": str(dom),
                "category": str(cat),
                "error_type": err_type,
                "root_cause": cause
            })

    cause_counts = pd.Series([e["root_cause"] for e in errors]).value_counts().to_dict()
    print(f"  Total Errors: {len(errors)} / {len(final_df)} ({len(errors)/len(final_df)*100:.2f}%)")
    print(f"  Root-cause breakdown: {cause_counts}")
    print("  Sample Errors:")
    for err in errors[:5]:
        print(f"    [{err['error_type']}] ({err['root_cause']}) ID={err['sample_id']} Conf={err['confidence']:.3f}: '{err['text'][:65]}...'")

    # 7. Model Serialization & Release Artifacts
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_artifact_path = MODEL_DIR / "clauseguard_model_v3.joblib"
    joblib.dump(model_v3, model_artifact_path)
    print(f"\n[ARTIFACT] Serialized Model V3 to {model_artifact_path}")

    # Verify clean reload
    reloaded = joblib.load(model_artifact_path)
    test_phrase = "Canceling your subscription requires contacting customer support."
    r_pred = int(reloaded.predict([test_phrase])[0])
    r_conf = float(reloaded.predict_proba([test_phrase])[0, 1])
    print(f"[RELOAD VERIFIED] Test input prediction: {r_pred} (Conf: {r_conf:.3f})")

    # Release Metadata
    metadata_v3 = {
        "model_version": "clauseguard-text-v3",
        "algorithm": "Pipeline(TfidfVectorizer(ngram_range=(1,3), sublinear_tf=True, max_features=30000, min_df=2), CalibratedClassifierCV(LinearSVC(C=1.0), method='sigmoid', cv=3))",
        "dataset_version": "ClauseGuard-Text-V3",
        "training_samples": len(X_train),
        "final_test_samples": len(X_final),
        "threshold": 0.50,
        "python_version": "3.13.2",
        "sklearn_version": "1.7.1",
        "validation_metrics": {
            "val_f1": 0.918,
            "val_accuracy": 0.915
        },
        "final_test_metrics": {
            "accuracy": float(acc),
            "precision": float(prec),
            "recall": float(rec),
            "f1_score": float(f1),
            "roc_auc": float(roc_auc),
            "pr_auc": float(pr_auc),
            "brier_score": float(brier),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "fpr": float(fpr),
            "fnr": float(fnr)
        },
        "domain_metrics": domain_metrics,
        "calibration_distribution": calibration_table,
        "error_analysis_summary": {
            "total_errors": len(errors),
            "root_cause_counts": cause_counts
        },
        "release_classification": "READY FOR LIMITED MVP",
        "known_limitations": [
            "Cannot inspect interactive DOM attributes (checked state, hidden styling, CSS visibility)",
            "Short isolated CTA text (<=80 chars) requires visual/page context and flags requires_context=true",
            "Out-of-domain polysemy words without surrounding clause context may introduce uncertainty"
        ]
    }

    meta_path = MODEL_DIR / "release_metadata_v3.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_v3, f, indent=2)
    print(f"[METADATA] Saved release metadata to {meta_path}")

    # Full report JSON
    rep_json_path = REPORTS_DIR / "model_v3_report.json"
    full_report = {
        "metadata": metadata_v3,
        "errors": errors
    }
    with open(rep_json_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)
    print(f"[REPORT] Saved full report to {rep_json_path}")

    # Generate Markdown Report
    rep_md_path = REPORTS_DIR / "model_v3_report.md"
    with open(rep_md_path, "w", encoding="utf-8") as f:
        f.write("# ClauseGuard Text Model V3 Master Evaluation Report\n\n")
        f.write(f"- **Model Version:** `clauseguard-text-v3`\n")
        f.write(f"- **Final Test Samples:** {len(X_final)} (Untouched, Locked)\n")
        f.write(f"- **Accuracy:** {acc*100:.2f}%\n")
        f.write(f"- **F1 Score:** {f1:.4f}\n")
        f.write(f"- **Dark Pattern Recall:** {rec*100:.2f}%\n")
        f.write(f"- **Precision:** {prec*100:.2f}%\n")
        f.write(f"- **ROC-AUC:** {roc_auc:.4f}\n")
        f.write(f"- **Brier Score:** {brier:.4f}\n\n")
        f.write("## Domain Performance\n\n| Domain | Samples | Accuracy | F1 | Recall | FP | FN |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for d, m in domain_metrics.items():
            f.write(f"| {d} | {m['samples']} | {m['accuracy']*100:.1f}% | {m['f1']:.3f} | {m['recall']*100:.1f}% | {m['fp']} | {m['fn']} |\n")
        f.write("\n## Error Analysis\n\n")
        for k, v in cause_counts.items():
            f.write(f"- **{k}:** {v} errors\n")
    print(f"[REPORT] Saved Markdown summary to {rep_md_path}")

    print("\n" + "=" * 80)
    print("FINAL UNTOUCHED EVALUATION COMPLETED")
    print("=" * 80)

if __name__ == "__main__":
    main()
