"""scripts/ablation_study_v3.py
Executes Section 32 Ablation Study:
Controlled comparisons of data additions on generalization:
- Ablation A: Unified real dataset only (EC + Edinburgh)
- Ablation B: Unified real dataset + hard negatives
- Ablation C: Unified real dataset + hard positives
- Ablation D: Unified real dataset + contrastive pairs
- Ablation E: Full dataset (all curated additions)

Evaluates each ablation on:
1. Validation F1
2. Hard Test / Polysemy F1 & False Positives
3. Contrastive Pair Accuracy
"""
import os
import sys
import json
import pathlib
import pandas as pd
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"

RANDOM_SEED = 42

OPTIMAL_VEC_CONFIG = {
    "ngram_range": (1, 3),
    "sublinear_tf": True,
    "max_features": 30000,
    "min_df": 2
}

def evaluate_on_sets(pipe, val_df, hard_df):
    val_preds = pipe.predict(val_df["text"].fillna(""))
    val_f1 = f1_score(val_df["label"].astype(int), val_preds, zero_division=0)
    val_acc = accuracy_score(val_df["label"].astype(int), val_preds)

    hard_preds = pipe.predict(hard_df["text"].fillna(""))
    y_hard = hard_df["label"].astype(int)
    hard_f1 = f1_score(y_hard, hard_preds, zero_division=0)
    hard_acc = accuracy_score(y_hard, hard_preds)
    hard_fp = int(sum((hard_preds == 1) & (y_hard == 0)))
    hard_fn = int(sum((hard_preds == 0) & (y_hard == 1)))

    # Contrastive check
    contrast_pairs = [
        ("The trial ends on October 14 and the renewal price is shown clearly.",
         "The renewal price is hidden until after payment information is entered."),
        ("Only three colors are currently available in stock.",
         "Only three left — buy now before they disappear forever!"),
        ("You can cancel the subscription from Account Settings.",
         "Canceling requires contacting customer support by phone.")
    ]
    flips = 0
    for norm, dark in contrast_pairs:
        p_n = pipe.predict_proba([norm])[0, 1]
        p_d = pipe.predict_proba([dark])[0, 1]
        if p_n < 0.5 and p_d >= 0.5:
            flips += 1
    contrast_acc = flips / len(contrast_pairs)

    return {
        "val_accuracy": float(val_acc),
        "val_f1": float(val_f1),
        "hard_accuracy": float(hard_acc),
        "hard_f1": float(hard_f1),
        "hard_fp": hard_fp,
        "hard_fn": hard_fn,
        "contrast_acc": float(contrast_acc)
    }

def main():
    print("=" * 80)
    print("CLAUSEGUARD V3: SECTION 32 ABLATION STUDY")
    print("=" * 80)

    train_base = pd.read_csv(DATA_DIR / "train_v3.csv")
    val_df = pd.read_csv(DATA_DIR / "validation_v3.csv")
    hard_df = pd.read_csv(DATA_DIR / "hard_test_v3.csv")

    # Filter base real dataset (EC + Edinburgh)
    is_real = train_base["source_dataset"].isin(["ec_darkpattern", "edinburgh_cookie_dialogs"])
    df_real = train_base[is_real].copy()

    # Load all curated records from build_dataset_v3 load function
    from scripts.build_dataset_v3 import load_curated_multi_domain
    curated_records = load_curated_multi_domain()
    df_curated = pd.DataFrame(curated_records)

    # Define Ablations
    # A: Real only
    abl_a = df_real.copy()

    # B: Real + Hard Negatives
    df_neg = df_curated[df_curated["difficulty"] == "hard_negative"].copy()
    abl_b = pd.concat([df_real, df_neg], ignore_index=True)

    # C: Real + Hard Positives (from contrastive dark pairs)
    df_pos = df_curated[(df_curated["difficulty"] == "hard_contrastive") & (df_curated["label"] == 1)].copy()
    abl_c = pd.concat([df_real, df_pos], ignore_index=True)

    # D: Real + Contrastive Pairs (both normal & dark)
    df_cont = df_curated[df_curated["difficulty"] == "hard_contrastive"].copy()
    abl_d = pd.concat([df_real, df_cont], ignore_index=True)

    # E: Full (Real + All Curated additions)
    abl_e = pd.concat([df_real, df_curated], ignore_index=True)

    ablations = {
        "Ablation A (Real Only)": abl_a,
        "Ablation B (Real + Hard Negatives)": abl_b,
        "Ablation C (Real + Hard Positives)": abl_c,
        "Ablation D (Real + Contrastive Pairs)": abl_d,
        "Ablation E (Full Dataset)": abl_e
    }

    results = {}
    for name, df_train in ablations.items():
        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(**OPTIMAL_VEC_CONFIG)),
            ("clf", CalibratedClassifierCV(
                estimator=LinearSVC(C=1.0, max_iter=2000, random_state=RANDOM_SEED),
                method="sigmoid",
                cv=3
            ))
        ])
        pipe.fit(df_train["text"].fillna(""), df_train["label"].astype(int))
        res = evaluate_on_sets(pipe, val_df, hard_df)
        results[name] = res
        print(f"\n{name} (Train N={len(df_train)}):")
        print(f"  Val F1:        {res['val_f1']:.3f} | Val Acc: {res['val_accuracy']*100:.1f}%")
        print(f"  Hard Test F1:  {res['hard_f1']:.3f} | Hard FP: {res['hard_fp']} (out of 50)")
        print(f"  Contrast Acc:  {res['contrast_acc']*100:.1f}%")

    out_path = REPORTS_DIR / "ablation_study_v3_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[REPORT] Saved ablation report to {out_path}")

if __name__ == "__main__":
    main()
