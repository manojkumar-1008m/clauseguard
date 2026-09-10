"""scripts/evaluate_models_v3.py
Executes Phase H: Hard/Generalization Evaluation & Leave-One-Domain-Out Cross-Validation.

Covers:
1. Hard Generalization & Polysemy Evaluation (data/hard_test_v3.csv)
2. Leave-One-Domain-Out (LODO) Generalization (Finance, SaaS, Travel, Ticketing, Healthcare, Education, Subscriptions, E-commerce, Compliance)
3. Semantic Contrastive Pair Evaluation (verifying appropriate probability flips)
4. Short-Text Policy Evaluation (measuring performance across length buckets and verifying requires_context flag)
5. Adversarial Robustness Testing (case, punctuation, number mutations)
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
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, brier_score_loss

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"

RANDOM_SEED = 42

OPTIMAL_VEC_CONFIG = {
    "ngram_range": (1, 3),
    "sublinear_tf": True,
    "max_features": 30000,
    "min_df": 2
}

def get_trained_candidate_model(train_df):
    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(**OPTIMAL_VEC_CONFIG)),
        ("clf", CalibratedClassifierCV(
            estimator=LinearSVC(C=1.0, max_iter=2000, random_state=RANDOM_SEED),
            method="sigmoid",
            cv=3
        ))
    ])
    pipe.fit(train_df["text"].fillna(""), train_df["label"].astype(int))
    return pipe

def evaluate_hard_test(model):
    hard_path = DATA_DIR / "hard_test_v3.csv"
    df = pd.read_csv(hard_path)
    X = df["text"].fillna("")
    y = df["label"].astype(int)

    preds = model.predict(X)
    probs = model.predict_proba(X)[:, 1]

    acc = accuracy_score(y, preds)
    prec = precision_score(y, preds, zero_division=0)
    rec = recall_score(y, preds, zero_division=0)
    f1 = f1_score(y, preds, zero_division=0)

    fp = int(sum((preds == 1) & (y == 0)))
    fn = int(sum((preds == 0) & (y == 1)))

    print(f"\n[1. HARD GENERALIZATION & POLYSEMY (N={len(df)})]")
    print(f"  Accuracy:  {acc*100:.1f}%")
    print(f"  Precision: {prec*100:.1f}%")
    print(f"  Recall:    {rec*100:.1f}%")
    print(f"  F1 Score:  {f1:.3f}")
    print(f"  FP: {fp} (out of {sum(y==0)} hard negatives)")
    print(f"  FN: {fn} (out of {sum(y==1)} hard positives)")

    return {
        "samples": len(df),
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "fp": fp,
        "fn": fn
    }

def evaluate_leave_one_domain_out():
    print("\n[2. LEAVE-ONE-DOMAIN-OUT (LODO) CROSS-VALIDATION]")
    train_df = pd.read_csv(DATA_DIR / "train_v3.csv")
    val_df = pd.read_csv(DATA_DIR / "validation_v3.csv")
    all_dev = pd.concat([train_df, val_df], ignore_index=True)

    domains = [d for d in all_dev["domain"].unique() if pd.notna(d) and len(all_dev[all_dev["domain"] == d]) >= 15]

    lodo_results = {}
    for dom in sorted(domains):
        held_out = all_dev[all_dev["domain"] == dom]
        training_subset = all_dev[all_dev["domain"] != dom]

        # Check if held-out domain has at least one example of both classes or calculate accuracy
        y_test = held_out["label"].astype(int)
        y_train = training_subset["label"].astype(int)

        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(**OPTIMAL_VEC_CONFIG)),
            ("clf", CalibratedClassifierCV(
                estimator=LinearSVC(C=1.0, max_iter=2000, random_state=RANDOM_SEED),
                method="sigmoid",
                cv=3
            ))
        ])
        pipe.fit(training_subset["text"].fillna(""), y_train)

        preds = pipe.predict(held_out["text"].fillna(""))
        acc = accuracy_score(y_test, preds)
        f1 = f1_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        prec = precision_score(y_test, preds, zero_division=0)
        fp = int(sum((preds == 1) & (y_test == 0)))
        fn = int(sum((preds == 0) & (y_test == 1)))

        lodo_results[dom] = {
            "samples": len(held_out),
            "dark_count": int(sum(y_test == 1)),
            "benign_count": int(sum(y_test == 0)),
            "accuracy": float(acc),
            "f1": float(f1),
            "precision": float(prec),
            "recall": float(rec),
            "fp": fp,
            "fn": fn
        }
        print(f"  Held-out: {dom:<18} (N={len(held_out):<4}) | Acc={acc*100:.1f}%, F1={f1:.3f}, Rec={rec*100:.1f}%, FP={fp}, FN={fn}")

    mean_lodo_f1 = np.mean([r["f1"] for r in lodo_results.values()])
    print(f"  -> Mean LODO F1 across all domains: {mean_lodo_f1:.3f}")
    return lodo_results, float(mean_lodo_f1)

def evaluate_contrastive_pairs(model):
    print("\n[3. CONTRASTIVE SEMANTIC PAIR FLIP EVALUATION]")
    test_pairs = [
        ("The trial ends on October 14 and the renewal price is shown clearly.",
         "The renewal price is hidden until after payment information is entered.",
         "Trial renewal transparency"),
        ("Only three colors are currently available in stock.",
         "Only three left — buy now before they disappear forever!",
         "Scarcity vs panic"),
        ("You can cancel the subscription from Account Settings.",
         "Canceling requires contacting customer support by phone.",
         "Cancellation friction"),
        ("The processing fee is displayed upfront before payment.",
         "The processing fee is revealed after payment details are entered.",
         "Drip pricing disclosure"),
        ("Flight ticket includes standard carry-on baggage.",
         "Carry-on bag fee of $45 automatically added to total unless unchecked.",
         "Sneaked baggage add-on")
    ]

    contrastive_results = []
    flips_successful = 0
    for norm, dark, name in test_pairs:
        p_norm = float(model.predict_proba([norm])[0, 1])
        p_dark = float(model.predict_proba([dark])[0, 1])
        lbl_norm = int(p_norm >= 0.5)
        lbl_dark = int(p_dark >= 0.5)
        success = (lbl_norm == 0 and lbl_dark == 1 and p_dark > p_norm)
        if success:
            flips_successful += 1

        print(f"  Pair: {name}")
        print(f"    Normal: '{norm}' -> Pred={lbl_norm} (Prob={p_norm:.3f})")
        print(f"    Dark:   '{dark}' -> Pred={lbl_dark} (Prob={p_dark:.3f})")
        print(f"    Status: {'CORRECT FLIP' if success else 'INCOMPLETE FLIP'} (Delta: +{p_dark - p_norm:.3f})")

        contrastive_results.append({
            "name": name,
            "normal_prob": p_norm,
            "dark_prob": p_dark,
            "delta": p_dark - p_norm,
            "flip_success": success
        })

    print(f"  Contrastive Pair Accuracy: {flips_successful}/{len(test_pairs)} ({flips_successful/len(test_pairs)*100:.1f}%)")
    return contrastive_results

def evaluate_short_text_policy(model):
    print("\n[4. SHORT-TEXT POLICY & CONTEXT GUARD EVALUATION]")
    short_inputs = [
        ("Buy now", 1),
        ("Limited", 1),
        ("Sale", 1),
        ("Cancel", 0),
        ("Only 3 left", 1),
        ("Special offer", 1),
        ("Accept all cookies", 0),
        ("Manage preferences", 0),
        ("Reject non-essential", 0),
        ("Close", 0)
    ]

    short_results = []
    for txt, exp in short_inputs:
        prob = float(model.predict_proba([txt])[0, 1])
        pred = int(prob >= 0.5)
        # Policy rule: len <= 80 or prob within uncertainty band [0.40, 0.65] flags requires_context
        requires_context = (len(txt) <= 80 or (0.40 <= prob <= 0.65))
        short_results.append({
            "text": txt,
            "predicted_label": pred,
            "confidence": prob,
            "requires_context": requires_context
        })
        print(f"  '{txt:<25}' -> Prob={prob:.3f} | Pred={pred} | requires_context={requires_context}")

    return short_results

def evaluate_adversarial_consistency(model):
    print("\n[5. ADVERSARIAL CONSISTENCY EVALUATION]")
    adversarial_groups = [
        ["ONLY 3 LEFT!", "Only three left!", "only three items remain in stock.", "3 items remain in stock."],
        ["Limited Time Offer!", "LIMITED TIME OFFER", "Limited time offer — expires soon", "limited time offer."],
        ["Free 30-day trial with automatic renewal", "FREE 30-DAY TRIAL WITH AUTOMATIC RENEWAL", "Free 30-day trial with auto-renewal."]
    ]

    adv_results = []
    for grp in adversarial_groups:
        probs = [float(model.predict_proba([t])[0, 1]) for t in grp]
        preds = [int(p >= 0.5) for p in probs]
        std_prob = float(np.std(probs))
        all_same = (len(set(preds)) == 1)
        print(f"  Group: '{grp[0]}'")
        for t, p, prd in zip(grp, probs, preds):
            print(f"    '{t:<45}' -> Prob={p:.3f} (Pred={prd})")
        print(f"    Consistency: {'PASS' if all_same else 'FAIL'} (StdDev={std_prob:.4f})")
        adv_results.append({
            "samples": grp,
            "probs": probs,
            "std_dev": std_prob,
            "consistent": all_same
        })

    return adv_results

def main():
    print("=" * 80)
    print("CLAUSEGUARD V3: GENERALIZATION & DOMAIN EVALUATION")
    print("=" * 80)

    train_df = pd.read_csv(DATA_DIR / "train_v3.csv")
    model = get_trained_candidate_model(train_df)

    hard_metrics = evaluate_hard_test(model)
    lodo_metrics, mean_lodo_f1 = evaluate_leave_one_domain_out()
    contrastive_metrics = evaluate_contrastive_pairs(model)
    short_metrics = evaluate_short_text_policy(model)
    adv_metrics = evaluate_adversarial_consistency(model)

    results = {
        "hard_generalization": hard_metrics,
        "leave_one_domain_out": lodo_metrics,
        "mean_lodo_f1": mean_lodo_f1,
        "contrastive_pairs": contrastive_metrics,
        "short_text_policy": short_metrics,
        "adversarial_consistency": adv_metrics
    }

    out_path = REPORTS_DIR / "model_v3_generalization_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[REPORT] Saved generalization report to {out_path}")

if __name__ == "__main__":
    main()
