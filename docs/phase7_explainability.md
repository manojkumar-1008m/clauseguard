# Phase 7.1: ClauseGuard Explainability & Pattern Detection Service

> **Important Notice:** This phase detects potential dark patterns from text and does not make legal determinations. It predicts potential design patterns based solely on textual interface phrasing and does not claim illegality, fraud, or statutory violation.

---

## 1. Architecture

Phase 7.1 upgrades ClauseGuard from a binary classifier into an explainable potential-dark-pattern detection pipeline.

```
                  USER-FACING INTERFACE TEXT
                              ↓
              PREPROCESSING (Whitespace / Encoding)
                              ↓
              V3 CLASSIFIER (Frozen TF-IDF + LinearSVC)
                              ↓
         [Calibrated Confidence & Initial Classification]
                              ↓
                 PATTERN MAPPING LAYER (Rules & Contradiction Audit)
                              ↓
                EVIDENCE EXTRACTION (Deterministic Substring Span)
                              ↓
               CONSUMER CONSEQUENCE ENGINE (Objective Risk Context)
                              ↓
           EXPLAINABLE RISK RESPONSE (FastAPI Pydantic Response)
```

---

## 2. Pattern Taxonomy

ClauseGuard categorizes detected patterns into 11 standardized classes:

1. **Subscription Trap:** Stealth automatic renewals, free-to-paid auto-conversions, and recurring billing without advance notice.
2. **Drip Pricing:** Concealing mandatory fees (e.g. resort, service, documentation fees) until late in the checkout journey.
3. **Obstruction:** Introducing artificial friction into cancellation flows (e.g. requiring phone calls or support tickets).
4. **Sneaking:** Automatically adding unrequested products, warranties, or services to cart.
5. **Scarcity:** Asserting low stock or limited unit counts to induce immediate purchasing.
6. **Urgency:** Countdown timers, expiration warnings, and artificial deadlines.
7. **Confirm Shaming:** Using emotionally manipulative language in opt-out or decline buttons to induce guilt.
8. **Social Proof:** Displaying peer activity indicators or viewer counts to pressure purchase decisions.
9. **Forced Action:** Mandating account creation or data disclosure before allowing users to proceed.
10. **Misdirection:** Visually or textually favoring one option while obscuring standard choices.
11. **Other:** Generalized manipulative interface phrasing not captured by specific categories.

---

## 3. Pattern Mapping Approach

Implemented in [`backend/services/pattern_mapper.py`](file:///c:/Users/rog/OneDrive/Desktop/clauseguard/backend/services/pattern_mapper.py).

The mapper operates deterministically above the machine learning model:
- **Contradiction Guards:** Inspects whether the surrounding context clearly contradicts deceptive intent (e.g., upfront fee disclosures: *"the processing fee is displayed clearly before payment"*; self-serve cancellation: *"cancel your subscription at any time from Account Settings"*; factual variants: *"only three colors are currently available"*). When a contradiction guard is met, false-positive keyword triggers are overridden to benign.
- **Multi-Signal Detection:** Requires combinations of indicative signals rather than isolated keywords to confirm a pattern.

---

## 4. Evidence Extraction Approach

Implemented in [`backend/services/evidence_extractor.py`](file:///c:/Users/rog/OneDrive/Desktop/clauseguard/backend/services/evidence_extractor.py).

- Extracts the smallest meaningful textual span demonstrating the pattern rather than repeating the entire document.
- Uses targeted category regex spans and sentence boundary segmentation while preserving original casing, punctuation, and currency symbols (e.g. ₹, $, €).

---

## 5. Consumer Consequence Generation

Implemented in [`backend/services/consequence_engine.py`](file:///c:/Users/rog/OneDrive/Desktop/clauseguard/backend/services/consequence_engine.py).

- Generates clear, consumer-facing explanations using potential phrasing (*"may"*, *"could"*, *"appears to"*, *"potentially"*).
- Interpolates specific monetary amounts and cadences (e.g. *"The subscription may renew automatically and result in a recurring ₹999 charge."*).

---

## 6. Short-Text Context Guard

- Input phrases $\le 80$ characters or having confidence within uncertainty ranges flag `requires_context: true`.
- For isolated commands (e.g. *"Buy now"*, *"Limited"*, *"Special offer"*), the system refuses confident category assignment, returning `pattern_category: null` and `requires_context: true`.

---

## 7. API Response Format

Endpoint: `POST /predict`

### Potential Dark Pattern Example:
```json
{
  "prediction": 1,
  "label": "potential_dark_pattern",
  "confidence": 0.75,
  "model_version": "clauseguard-text-v3",
  "requires_context": false,
  "pattern_category": "Subscription Trap",
  "evidence": "automatically renews at ₹999/month",
  "consumer_consequence": "The subscription may renew automatically and result in a recurring ₹999 charge."
}
```

### Benign Example:
```json
{
  "prediction": 0,
  "label": "not_dark_pattern",
  "confidence": 0.15,
  "model_version": "clauseguard-text-v3",
  "requires_context": false,
  "pattern_category": null,
  "evidence": null,
  "consumer_consequence": null
}
```

### Short-Text Context Required Example:
```json
{
  "prediction": 1,
  "label": "potential_dark_pattern",
  "confidence": 0.70,
  "model_version": "clauseguard-text-v3",
  "requires_context": true,
  "pattern_category": null,
  "evidence": "Buy now",
  "consumer_consequence": null
}
```

---

## 8. Test Results

- **Total Tests:** 47 automated tests (`pytest -q`)
- **Passed:** 47 / 47 (100% pass rate)
- **Failed:** 0
- **Regression:** Zero regressions across existing API, extension contract, and security test suites.

---

## 9. Limitations & Future Scope

1. **Text-Only Boundary:** The service cannot inspect interactive DOM properties (e.g. pre-checked checkboxes, hidden input styling, CSS visual hierarchy).
2. **Deterministic Rules:** Text patterns not anticipated by the rule taxonomy will fallback to `"Other"`.
3. **Multimodal Road Map:** Future phases will integrate DOM structure rules and computer vision for complete interface risk fusion.
