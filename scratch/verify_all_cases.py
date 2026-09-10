import sys
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

cases = [
    ("STEP 12", "Your free trial automatically renews at \u20b9999/month after 7 days."),
    ("STEP 13", "Samsung TV \u2014 \u20b949,999"),
    ("STEP 14", "Ticket price is \u20b9499. A processing fee of \u20b979 applies."),
    ("STEP 15", "Price increased from \u20b9999 to \u20b91299.")
]

for label, text in cases:
    sys.stdout.buffer.write((f"=== {label} ===\n").encode("utf-8"))
    p = client.post("/predict", json={"text": text}).json()
    pr = client.post("/analyze-price", json={"text": text}).json()
    f = client.post("/fuse-evidence", json={"text": text, "text_prediction": p, "price_analysis": pr}).json()
    e = client.post("/explain", json={"fusion_response": f}).json()
    res = (
        f"  Text: {text}\n"
        f"  Risk Status: {e.get('risk_status')}\n"
        f"  Title: {e.get('title')}\n"
        f"  Summary: {e.get('summary')}\n"
        f"  Price - displayed: {pr.get('displayed_price')}, additional_cost: {pr.get('additional_cost')}, known_total: {pr.get('known_total')}\n"
        f"  Price - price_change: {pr.get('price_change')}, percentage: {pr.get('price_change_percentage')}\n"
        f"  Price - trial_price: {pr.get('trial_price')}, renewal_price: {pr.get('renewal_price')}\n"
    )
    sys.stdout.buffer.write(res.encode("utf-8"))
