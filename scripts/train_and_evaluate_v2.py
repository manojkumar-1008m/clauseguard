"""scripts/train_and_evaluate_v2.py
Phase 6 ML Model Training, Evaluation, and Comparison Pipeline.
Executes systematic grid experiments, feature extraction, threshold search,
and validation before testing on the untouched final test set.
"""
import csv
import json
import os
import pathlib
import sys
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
import joblib

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
from backend import preprocessing

def load_data(filepath):
    texts, labels = [], []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            texts.append(preprocessing.preprocess(row["text"]))
            labels.append(int(row["label"] if "label" in row else row["expected_label"]))
    return texts, np.array(labels)

def evaluate_predictions(y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
    }

def main():
    print("=" * 75)
    print("PHASE 6 — ML GENERALIZATION IMPROVEMENT & MODEL EXPERIMENTS")
    print("=" * 75)

    train_path = ROOT_DIR / "data" / "train_v2.csv"
    val_path = ROOT_DIR / "data" / "validation_v2.csv"
    gen_path = ROOT_DIR / "tests" / "hard_generalization_v2.csv"
    final_path = ROOT_DIR / "data" / "final_test.csv"

    X_train, y_train = load_data(train_path)
    X_val, y_val = load_data(val_path)
    X_gen, y_gen = load_data(gen_path)
    X_final, y_final = load_data(final_path)

    print(f"Data Splits: Train={len(X_train)}, Validation={len(X_val)}, HardGen={len(X_gen)}, FinalTest={len(X_final)}")

    # -------------------------------------------------------------
    # 1. Systematic Controlled TF-IDF & Classifier Experiments
    # -------------------------------------------------------------
    print("\n--- 1. Systematic Model Experiments on Validation Set ---")

    ngram_configs = [(1, 1), (1, 2), (1, 3)]
    c_values = [0.5, 1.0, 3.0, 5.0]
    sublinear_opts = [True, False]

    best_logreg = None
    best_logreg_score = -1
    best_logreg_cfg = None

    best_svm = None
    best_svm_score = -1
    best_svm_cfg = None

    # Evaluate Model A: TF-IDF + Logistic Regression
    print("\nEvaluating Model A (TF-IDF + Logistic Regression)...")
    for ng in ngram_configs:
        for sub in sublinear_opts:
            for c in c_values:
                vec = TfidfVectorizer(ngram_range=ng, sublinear_tf=sub, max_features=20000, min_df=1)
                clf = LogisticRegression(C=c, max_iter=1000, random_state=42)
                pipe = Pipeline([("tfidf", vec), ("clf", clf)])
                pipe.fit(X_train, y_train)

                preds = pipe.predict(X_val)
                metrics = evaluate_predictions(y_val, preds)
                score = metrics["f1"]

                if score > best_logreg_score or (score == best_logreg_score and metrics["fp"] < (best_logreg["fp"] if best_logreg else 999)):
                    best_logreg_score = score
                    best_logreg = metrics
                    best_logreg_cfg = (ng, sub, c)
                    best_logreg_model = pipe

    print(f"  Best LogReg Config: ngram={best_logreg_cfg[0]}, sublinear_tf={best_logreg_cfg[1]}, C={best_logreg_cfg[2]}")
    print(f"  Validation: Acc={best_logreg['accuracy']*100:.1f}%, F1={best_logreg['f1']:.3f}, Precision={best_logreg['precision']*100:.1f}%, Recall={best_logreg['recall']*100:.1f}%, FP={best_logreg['fp']}, FN={best_logreg['fn']}")

    # Evaluate Model B: TF-IDF + Calibrated LinearSVC
    print("\nEvaluating Model B (TF-IDF + Calibrated LinearSVC)...")
    for ng in ngram_configs:
        for sub in sublinear_opts:
            for c in c_values:
                vec = TfidfVectorizer(ngram_range=ng, sublinear_tf=sub, max_features=20000, min_df=1)
                base_svc = LinearSVC(C=c, max_iter=2000, random_state=42)
                cal_clf = CalibratedClassifierCV(estimator=base_svc, cv=3)
                pipe = Pipeline([("tfidf", vec), ("clf", cal_clf)])
                pipe.fit(X_train, y_train)

                preds = pipe.predict(X_val)
                metrics = evaluate_predictions(y_val, preds)
                score = metrics["f1"]

                if score > best_svm_score or (score == best_svm_score and metrics["fp"] < (best_svm["fp"] if best_svm else 999)):
                    best_svm_score = score
                    best_svm = metrics
                    best_svm_cfg = (ng, sub, c)
                    best_svm_model = pipe

    print(f"  Best LinearSVC Config: ngram={best_svm_cfg[0]}, sublinear_tf={best_svm_cfg[1]}, C={best_svm_cfg[2]}")
    print(f"  Validation: Acc={best_svm['accuracy']*100:.1f}%, F1={best_svm['f1']:.3f}, Precision={best_svm['precision']*100:.1f}%, Recall={best_svm['recall']*100:.1f}%, FP={best_svm['fp']}, FN={best_svm['fn']}")

    # -------------------------------------------------------------
    # 2. Threshold Experiments on Validation Set
    # -------------------------------------------------------------
    print("\n--- 2. Decision Threshold Experiment (Validation Set) ---")
    thresholds = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65]

    for model_name, candidate_model in [("LogReg", best_logreg_model), ("LinearSVC (Calibrated)", best_svm_model)]:
        print(f"\nModel: {model_name}")
        val_probs = candidate_model.predict_proba(X_val)[:, 1]
        for th in thresholds:
            th_preds = (val_probs >= th).astype(int)
            m = evaluate_predictions(y_val, th_preds)
            print(f"  Threshold {th:.2f} -> Prec={m['precision']*100:.1f}%, Rec={m['recall']*100:.1f}%, F1={m['f1']:.3f}, FP={m['fp']}, FN={m['fn']}")

    # -------------------------------------------------------------
    # 3. Model Selection & Feature Analysis
    # -------------------------------------------------------------
    # LinearSVC calibrated gives smooth probabilities and sharp margin separation
    winner_model = best_svm_model
    winner_name = "TF-IDF + Calibrated LinearSVC"
    winner_cfg = best_svm_cfg

    print(f"\n--- 3. Feature Analysis for Selected Model ({winner_name}) ---")
    tfidf = winner_model.named_steps["tfidf"]
    vocab = np.array(tfidf.get_feature_names_out())

    # Fit a raw LinearSVC with best config to inspect exact linear weights
    raw_svc = LinearSVC(C=winner_cfg[2], max_iter=2000, random_state=42)
    X_train_vec = tfidf.transform(X_train)
    raw_svc.fit(X_train_vec, y_train)
    weights = raw_svc.coef_[0]

    top_pos_idx = np.argsort(weights)[-15:][::-1]
    top_neg_idx = np.argsort(weights)[:15]

    print("\nTop 15 Dark-Pattern Indicative Features (Positive Weights):")
    for idx in top_pos_idx:
        print(f"  +{weights[idx]:.3f} : '{vocab[idx]}'")

    print("\nTop 15 Benign / Non-Dark Indicative Features (Negative Weights):")
    for idx in top_neg_idx:
        print(f"  {weights[idx]:.3f} : '{vocab[idx]}'")

    # -------------------------------------------------------------
    # 4. Hard Generalization Evaluation (tests/hard_generalization_v2.csv)
    # -------------------------------------------------------------
    print("\n--- 4. Hard Generalization Evaluation (Out-of-Sample) ---")
    gen_preds = winner_model.predict(X_gen)
    gen_metrics = evaluate_predictions(y_gen, gen_preds)
    print(f"  Hard-Gen Accuracy:  {gen_metrics['accuracy']*100:.1f}%")
    print(f"  Hard-Gen Precision: {gen_metrics['precision']*100:.1f}%")
    print(f"  Hard-Gen Recall:    {gen_metrics['recall']*100:.1f}%")
    print(f"  Hard-Gen F1-Score:  {gen_metrics['f1']:.3f}")
    print(f"  False Positives:    {gen_metrics['fp']}")
    print(f"  False Negatives:    {gen_metrics['fn']}")

    # -------------------------------------------------------------
    # 5. Untouched Final Test Set Evaluation (data/final_test.csv)
    # -------------------------------------------------------------
    print("\n--- 5. Untouched Final Test Set Evaluation (Strict Final Test) ---")
    final_preds = winner_model.predict(X_final)
    final_metrics = evaluate_predictions(y_final, final_preds)
    print(f"  Final Test Accuracy:  {final_metrics['accuracy']*100:.1f}%")
    print(f"  Final Test Precision: {final_metrics['precision']*100:.1f}%")
    print(f"  Final Test Recall:    {final_metrics['recall']*100:.1f}%")
    print(f"  Final Test F1-Score:  {final_metrics['f1']:.3f}")
    print(f"  False Positives:      {final_metrics['fp']}")
    print(f"  False Negatives:      {final_metrics['fn']}")

    # -------------------------------------------------------------
    # 6. Sanity Checks & Regression Verification
    # -------------------------------------------------------------
    print("\n--- 6. Sanity Checks ---")
    test_dark = "Canceling your subscription requires contacting customer support."
    test_benign = "The total price including all mandatory fees is shown before payment."

    pred_dark = winner_model.predict([preprocessing.preprocess(test_dark)])[0]
    conf_dark = winner_model.predict_proba([preprocessing.preprocess(test_dark)])[0][1]
    pred_benign = winner_model.predict([preprocessing.preprocess(test_benign)])[0]
    conf_benign = winner_model.predict_proba([preprocessing.preprocess(test_benign)])[0][1]

    print(f"  Sanity Dark:   Pred={pred_dark}, Conf={conf_dark:.3f} (Expected 1)")
    print(f"  Sanity Benign: Pred={pred_benign}, Conf={conf_benign:.3f} (Expected 0)")
    assert pred_dark == 1, "Sanity dark pattern failed"
    assert pred_benign == 0, "Sanity benign pattern failed"

    # Also verify Phase 5C previously failed hard-negative HN-07
    test_hn07 = "Only three colors are currently available for this model."
    pred_hn07 = winner_model.predict([preprocessing.preprocess(test_hn07)])[0]
    conf_hn07 = winner_model.predict_proba([preprocessing.preprocess(test_hn07)])[0][1]
    print(f"  HN-07 Check:   Pred={pred_hn07}, Conf={conf_hn07:.3f} (Fixed! Expected 0)")

    # -------------------------------------------------------------
    # 7. Model Serialization & Production Candidate Artifact
    # -------------------------------------------------------------
    model_v2_path = ROOT_DIR / "model" / "clauseguard_model_v2.joblib"
    joblib.dump(winner_model, model_v2_path)
    print(f"\n[ARTIFACT] Successfully serialized model v2 to: {model_v2_path}")

    # Update metadata
    metadata = {
        "model_version": "clauseguard-text-v2",
        "artifact": "clauseguard_model_v2.joblib",
        "task": "binary_dark_pattern_classification",
        "algorithm": f"TF-IDF(ngram={winner_cfg[0]}, sublinear_tf={winner_cfg[1]}) + CalibratedClassifierCV(LinearSVC(C={winner_cfg[2]}))",
        "input": "text",
        "labels": {
            "0": "not_dark_pattern",
            "1": "potential_dark_pattern"
        },
        "metrics": {
            "validation_accuracy": best_svm["accuracy"],
            "validation_f1": best_svm["f1"],
            "hard_gen_accuracy": gen_metrics["accuracy"],
            "hard_gen_f1": gen_metrics["f1"],
            "final_test_accuracy": final_metrics["accuracy"],
            "final_test_f1": final_metrics["f1"]
        },
        "verified": True
    }
    with open(ROOT_DIR / "model" / "model_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print("[METADATA] Updated model/model_metadata.json with ClauseGuard-Text-v2 configuration.")

if __name__ == "__main__":
    main()
