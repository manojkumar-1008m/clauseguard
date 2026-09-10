"""scripts/train_models_v3.py
Executes Phase G: Classical Model Training & Comparison for ClauseGuard V3.

Trains & benchmarks:
- Model A: TF-IDF + Logistic Regression L2
- Model B: TF-IDF + Logistic Regression L1 (sparse)
- Model C: TF-IDF + RidgeClassifier
- Model D: TF-IDF + LinearSVC
- Model E: TF-IDF + Calibrated LinearSVC (sigmoid)

Evaluates strictly on validation_v3.csv.
Analyzes top positive/negative coefficients and probability calibration.
"""
import os
import sys
import json
import time
import pathlib
import pandas as pd
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    brier_score_loss
)

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
MODEL_DIR = ROOT_DIR / "model"

RANDOM_SEED = 42

def compute_all_metrics(y_true, y_pred, y_prob=None):
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
    
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    
    roc_auc = float(roc_auc_score(y_true, y_prob)) if y_prob is not None else None
    pr_auc = float(average_precision_score(y_true, y_prob)) if y_prob is not None else None
    brier = float(brier_score_loss(y_true, y_prob)) if y_prob is not None else None
    
    return {
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "dark_recall": float(rec),
        "dark_f1": float(f1),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "fpr": float(fpr),
        "fnr": float(fnr),
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "brier_score": brier
    }

def main():
    print("=" * 80)
    print("CLAUSEGUARD V3: CLASSICAL MODEL EXPERIMENTS (MODELS A-E)")
    print("=" * 80)

    # 1. Load Training and Validation Sets
    train_df = pd.read_csv(DATA_DIR / "train_v3.csv")
    val_df = pd.read_csv(DATA_DIR / "validation_v3.csv")

    X_train, y_train = train_df["text"].fillna(""), train_df["label"].astype(int)
    X_val, y_val = val_df["text"].fillna(""), val_df["label"].astype(int)

    print(f"Loaded Train: {len(X_train)} samples, Validation: {len(X_val)} samples.")

    # 2. Vectorizer Parameter Exploration on Validation
    print("\n[TF-IDF EXPERIMENTS ON VALIDATION]")
    vectorizer_configs = [
        {"ngram_range": (1, 1), "sublinear_tf": True, "max_features": 20000, "min_df": 1},
        {"ngram_range": (1, 2), "sublinear_tf": True, "max_features": 20000, "min_df": 1},
        {"ngram_range": (1, 2), "sublinear_tf": False, "max_features": 20000, "min_df": 1},
        {"ngram_range": (1, 3), "sublinear_tf": True, "max_features": 30000, "min_df": 2},
    ]

    best_v_cfg = None
    best_v_f1 = 0.0
    for v_cfg in vectorizer_configs:
        tfidf = TfidfVectorizer(**v_cfg)
        clf = LinearSVC(C=1.0, random_state=RANDOM_SEED, max_iter=2000)
        pipe = Pipeline([("tfidf", tfidf), ("clf", clf)])
        pipe.fit(X_train, y_train)
        preds = pipe.predict(X_val)
        f1 = f1_score(y_val, preds)
        print(f"  Config {v_cfg['ngram_range']} sublinear={v_cfg['sublinear_tf']} max_feat={v_cfg['max_features']} min_df={v_cfg['min_df']} -> Val F1: {f1:.4f}")
        if f1 > best_v_f1:
            best_v_f1 = f1
            best_v_cfg = v_cfg

    print(f"  -> Selected optimal vectorizer config: {best_v_cfg} with Val F1: {best_v_f1:.4f}")

    # 3. Model Comparisons
    models = {
        "Model A (LogReg L2)": LogisticRegression(penalty="l2", C=1.0, max_iter=2000, random_state=RANDOM_SEED),
        "Model B (LogReg L1)": LogisticRegression(penalty="l1", solver="liblinear", C=1.0, max_iter=2000, random_state=RANDOM_SEED),
        "Model C (Ridge)": RidgeClassifier(alpha=1.0, random_state=RANDOM_SEED),
        "Model D (LinearSVC)": LinearSVC(C=1.0, max_iter=2000, random_state=RANDOM_SEED),
        "Model E (Calibrated LinearSVC)": CalibratedClassifierCV(
            estimator=LinearSVC(C=1.0, max_iter=2000, random_state=RANDOM_SEED),
            method="sigmoid",
            cv=3
        )
    }

    comparison_results = {}
    fitted_pipelines = {}

    print("\n[TRAINING & EVALUATING MODELS A-E ON VALIDATION]")
    for name, clf in models.items():
        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(**best_v_cfg)),
            ("clf", clf)
        ])
        
        t0 = time.time()
        pipe.fit(X_train, y_train)
        fit_time = time.time() - t0

        t0_inf = time.time()
        preds = pipe.predict(X_val)
        inf_latency_ms = ((time.time() - t0_inf) / len(X_val)) * 1000.0

        # Extract probabilities or decision function if available
        probs = None
        if hasattr(pipe, "predict_proba"):
            probs = pipe.predict_proba(X_val)[:, 1]
        elif hasattr(pipe, "decision_function"):
            dfn = pipe.decision_function(X_val)
            # Min-max scale decision function as pseudo-prob for AUC
            probs = (dfn - dfn.min()) / (dfn.max() - dfn.min() + 1e-8)

        metrics = compute_all_metrics(y_val, preds, probs)
        metrics["fit_time_sec"] = fit_time
        metrics["inference_latency_ms"] = inf_latency_ms

        comparison_results[name] = metrics
        fitted_pipelines[name] = pipe

        print(f"  {name:<30}: Acc={metrics['accuracy']*100:.1f}%, F1={metrics['f1']:.3f}, Dark Rec={metrics['dark_recall']*100:.1f}%, FP={metrics['false_positives']}, FN={metrics['false_negatives']}")

    # 4. Feature Coefficient Analysis (Inspect suspicious keyword bias)
    print("\n[FEATURE COEFFICIENT ANALYSIS (LinearSVC)]")
    svc_pipe = fitted_pipelines["Model D (LinearSVC)"]
    feature_names = svc_pipe.named_steps["tfidf"].get_feature_names_out()
    coefs = svc_pipe.named_steps["clf"].coef_[0]

    top_pos_idx = np.argsort(coefs)[-20:][::-1]
    top_neg_idx = np.argsort(coefs)[:20]

    top_pos_features = [(feature_names[i], float(coefs[i])) for i in top_pos_idx]
    top_neg_features = [(feature_names[i], float(coefs[i])) for i in top_neg_idx]

    print("  Top Positive Features (Dark Pattern indicators):")
    for feat, weight in top_pos_features[:10]:
        print(f"    +{weight:.3f} : {feat}")

    print("  Top Negative Features (Benign indicators):")
    for feat, weight in top_neg_features[:10]:
        print(f"    {weight:.3f} : {feat}")

    # Check for suspicious single-word memorization
    suspicious_check = ["trial", "fee", "cancel", "return", "only", "days", "subscription"]
    feature_dict = {f: c for f, c in zip(feature_names, coefs)}
    print("\n  Weights of potentially polysemous keywords:")
    for w in suspicious_check:
        w_coef = feature_dict.get(w, 0.0)
        print(f"    Keyword '{w:<12}': weight = {w_coef:+.3f}")

    # 5. Threshold Tuning on Validation for Model E
    print("\n[THRESHOLD SENSITIVITY ON VALIDATION (Model E)]")
    cal_pipe = fitted_pipelines["Model E (Calibrated LinearSVC)"]
    val_probs = cal_pipe.predict_proba(X_val)[:, 1]
    threshold_results = {}
    
    thresholds = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
    for th in thresholds:
        th_preds = (val_probs >= th).astype(int)
        th_m = compute_all_metrics(y_val, th_preds, val_probs)
        threshold_results[str(th)] = th_m
        print(f"    Threshold {th:.2f}: Prec={th_m['precision']*100:.1f}%, Rec={th_m['recall']*100:.1f}%, F1={th_m['f1']:.3f}, FP={th_m['false_positives']}, FN={th_m['false_negatives']}")

    # Save detailed report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_data = {
        "best_vectorizer_config": best_v_cfg,
        "model_comparison": comparison_results,
        "top_positive_features": top_pos_features,
        "top_negative_features": top_neg_features,
        "polysemy_feature_weights": {w: feature_dict.get(w, 0.0) for w in suspicious_check},
        "threshold_tuning_model_e": threshold_results
    }
    
    report_path = REPORTS_DIR / "model_v3_validation_comparison.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\n[REPORT] Saved classical model comparison report to {report_path}")

if __name__ == "__main__":
    main()
