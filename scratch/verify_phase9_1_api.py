import sys
import requests
import json

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

print("--- 1. GET /health ---")
r = requests.get(f"{BASE_URL}/health")
print(f"Status: {r.status_code}")
print(f"Body: {r.json()}\n")
assert r.status_code == 200

cases = [
    ("Case 1: Normal price", "Samsung TV — ₹49,999"),
    ("Case 2: Subscription renewal", "Your free trial automatically renews at ₹999/month after 7 days."),
    ("Case 3: Additional fee", "Ticket price is ₹499. A processing fee of ₹79 applies."),
    ("Case 4: Price change", "Price increased from ₹999 to ₹1299."),
    ("Case 5: Alternative pricing", "Choose between ₹499 and ₹999."),
]

for label, text in cases:
    print(f"=== {label} ===")
    print(f"Text: '{text}'")

    # POST /predict
    r_pred = requests.post(f"{BASE_URL}/predict", json={"text": text})
    print(f"  POST /predict -> HTTP {r_pred.status_code} (pred={r_pred.json().get('prediction')}, pattern={r_pred.json().get('pattern_category')})")
    assert r_pred.status_code == 200

    # POST /analyze-price
    r_price = requests.post(f"{BASE_URL}/analyze-price", json={"text": text})
    print(f"  POST /analyze-price -> HTTP {r_price.status_code} (entities={len(r_price.json().get('entities', []))}, change={r_price.json().get('price_changed')}, renewal={r_price.json().get('renewal_price_detected')})")
    assert r_price.status_code == 200

    # POST /fuse-evidence
    r_fuse = requests.post(f"{BASE_URL}/fuse-evidence", json={"text": text})
    print(f"  POST /fuse-evidence -> HTTP {r_fuse.status_code}")
    fuse_data = r_fuse.json()
    print(f"    risk_detected: {fuse_data.get('risk_detected')}")
    print(f"    risk_level: {fuse_data.get('risk_level')}")
    print(f"    primary_pattern: {fuse_data.get('primary_pattern')}")
    print(f"    price_changed: {fuse_data.get('price_changed')}")
    print(f"    renewal_signal: {fuse_data.get('renewal_signal')}")
    print(f"    signals: {fuse_data.get('signals')}")
    assert r_fuse.status_code == 200

    # POST /explain
    r_exp = requests.post(f"{BASE_URL}/explain", json={"fusion_response": fuse_data})
    print(f"  POST /explain -> HTTP {r_exp.status_code} (risk_status={r_exp.json().get('risk_status')}, title='{r_exp.json().get('title')}')\n")
    assert r_exp.status_code == 200

print("ALL LIVE ENDPOINT TESTS PASSED SUCCESSFULLY!")
