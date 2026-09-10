# ClauseGuard Evidence Fusion Engine (Phase 8.6)

## 1. Purpose and Role
The **ClauseGuard Evidence Fusion Engine** (`backend/services/evidence_fusion.py`) operates as the central deterministic synthesis layer that bridges upstream specialized analyzers (Text Predictor, Pattern Mapper, Price Analyzer, UI/DOM Analyzer, Behavior Analyzer) and the downstream Risk Engine.

Its primary responsibility is to answer five fundamental architectural questions:
1. **What evidence exists?**
2. **Where did it come from?** (Provenance tracking)
3. **How do the signals relate?** (Cross-source corroboration)
4. **Are multiple sources describing the same consumer risk?** (Evidence grouping)
5. **What is the traceable consumer consequence?** (Structured financial and subscription impact)

> **Mandatory Architectural Invariant**:
> *"Evidence Fusion combines independently detected signals into a traceable evidence structure. It does not independently determine whether conduct is unlawful or conclusively classify a dark pattern."*

---

## 2. Architecture & Pipeline

```text
TEXT PREDICTOR ──────┐
      ↓              │
PATTERN MAPPER       │
      ↓              │
EVIDENCE EXTRACTOR   │
      ↓              │
CONSEQUENCE ENGINE   │
                     ├────────► EVIDENCE FUSION ENGINE ────────► RISK ASSESSMENT / ENGINE
PRICE ANALYZER ──────┤          (Phase 8.6)                      (Future Phase)
(Phases 8.1 - 8.5)   │          - Cross-source corroboration
                     │          - Traceable provenance
DOM / UI ANALYZER ───┤          - Conflict handling
(Future / External)  │          - Anti-double counting
                     │          - Deterministic scoring baseline
BEHAVIOR ANALYZER ───┘
(Future / External)
```

### Separation of Responsibilities
- **Text Predictor**: ML classification of dark patterns (`prediction`, `confidence`).
- **Pattern Mapper**: Normalized pattern taxonomy (`subscription_trap`, `drip_pricing`, etc.).
- **Evidence Extractor**: Textual substring spans and linguistic indicators.
- **Consequence Engine**: Consumer consequence derived from text alone.
- **Price Analyzer**: Extraction of monetary entities, fee totals, subscriptions, and price transitions.
- **Evidence Fusion**: Corroborates cross-modal evidence into unified groups, isolates financial signals from deceptive patterns, resolves contradictions, and computes a traceable baseline risk score.
- **Risk Engine** (Future): Final regulatory, jurisdictional, and consumer alert decisioning.

---

## 3. Input Contract & Schemas

Defined in `backend/schemas/evidence.py`:

### `EvidenceItem`
Every detected signal is normalized into an `EvidenceItem` with a deterministic, stable per-request identifier (`E001`, `E002`, ...):
- `evidence_id`: e.g. `"E001"`
- `source`: Allowed sources: `"text"`, `"price"`, `"dom"`, `"ui"`, `"behavior"`, `"history"`, `"rules"`.
- `type`: Specific signal type (e.g. `"subscription_trap"`, `"free_trial"`, `"renewal_price"`, `"countdown_timer"`, `"price_increase"`).
- `pattern`: Optional dark pattern category if applicable (e.g. `"subscription_trap"`, `"drip_pricing"`, `"urgency"`).
- `description`: Human-readable summary of the detected fact.
- `value`: Raw or structured value (e.g. `999.0`, `"₹999/month"`).
- `currency`: ISO 4217 code (e.g. `"INR"`, `"USD"`).
- `confidence`: Source confidence in `[0.0, 1.0]`.
- `character_start` / `character_end`: Position offsets in original input text.
- `severity`: `"low"`, `"medium"`, `"high"`, or `"critical"`.
- `provenance`: Originating component (e.g. `"text_predictor"`, `"price_analyzer"`).
- `metadata`: Additional diagnostic attributes.

### `EvidenceGroup`
Related evidence items describing the same underlying risk or interaction are bundled into an `EvidenceGroup`:
- `group_id`: e.g. `"G001"`
- `pattern`: e.g. `"subscription_risk"`, `"drip_pricing_risk"`, `"urgency_scarcity"`, `"price_change"`.
- `evidence_ids`: Ordered list of `EvidenceItem.evidence_id` values.
- `sources`: Unique list of contributing sources (e.g. `["text", "price"]`).
- `corroborated`: `true` if $\ge 2$ independent sources support the finding.

---

## 4. Cross-Source Corroboration & Relationships

The core capability of Evidence Fusion is detecting relationships across heterogeneous signals without resorting to black-box LLMs:

| Signal A (Source) | Signal B (Source) | Signal C (Source) | Fused Relationship | Group Classification |
|---|---|---|---|---|
| Text: `subscription_trap` | Price: `renewal_price` | Price: `trial_price = 0` | Free trial transitioning into recurring charge | Corroborated `subscription_risk` |
| Text: `drip_pricing` | Price: `additional_costs > 0` | Price: `late_disclosed = true` | Upfront base price followed by late fee | Corroborated `drip_pricing_risk` |
| Text: `urgency` / `scarcity` | DOM: `countdown_timer` | - | Artificial urgency pressure with live UI element | Corroborated `urgency_scarcity` |
| Price: `previous_price` | Price: `current_price` | - | Quantified price change (isolated financial fact) | Non-deceptive `price_change` |

### Multi-Signal Corroboration Rule
- A single isolated keyword (e.g. `"trial"`, `"sale"`, `"limited"`) is **never** sufficient for a high-risk finding.
- Cross-source corroboration triggers when $\ge 2$ distinct sources (e.g. `text` and `price`, or `text` and `dom`) corroborate the same underlying pattern.
- When corroborated, `is_corroborated = true`, boosting both score and confidence.

---

## 5. Deduplication & Anti-Double-Counting

A single transaction figure (e.g. `₹999/month`) often appears across multiple upstream analyzer fields:
- `displayed_price`
- `renewal_price`
- `later_price`

**Invariant**: The fusion engine represents the underlying monetary fact once:
- When a trial or renewal structure exists, `renewal_price` is tracked as the authoritative recurring cost.
- A redundant `displayed_price` matching the `renewal_price` without upfront charge is deduplicated and marked as `is_duplicate_renewal` to prevent double-counting risk points.
- Shared entity indices are reconciled during evidence item generation.

---

## 6. Contradiction & Conflict Handling

Conflicting evidence between analyzers (e.g. Text claims `"Free trial"` but Price Analyzer extracts a mandatory `₹99 trial fee`) is handled safely:
1. The engine **never** silently discards or overrides one source.
2. An `EvidenceConflict` object is generated:
   ```json
   {
       "type": "evidence_conflict",
       "sources": ["text", "price"],
       "description": "Conflict between text claim of free trial and price analyzer trial fee of ₹99.0",
       "resolution": "preserve_both"
   }
   ```
3. Both evidence items are preserved in the audit log.
4. A deterministic confidence penalty (`-0.20`) and score penalty (`CONFLICT_PENALTY = 1.0`) are applied to reflect data ambiguity.

---

## 7. Financial Signal vs. Potential Dark Pattern Separation

ClauseGuard maintains a strict distinction between pure financial signals and potential deceptive dark patterns:

- **Price Change Alone**:
  - `price_change_detected = true`
  - `financial_signal = true`
  - `dark_pattern = null`
  - A legitimate price increase (`from ₹999 to ₹1299`) is a financial signal, not a deceptive practice.
- **Uncorroborated Late Fee**:
  - Upfront price + fee without deceptive text indicators:
  - `financial_signal = true`
  - `potential_pattern = "late_disclosure_fee"`
  - `dark_pattern = null` (conservative baseline).
- **Corroborated Dark Pattern**:
  - `Text Predictor (drip_pricing) + Late Fee Disclosure`:
  - `potential_pattern = "drip_pricing"`
  - `dark_pattern = "drip_pricing"`
  - `corroborated = true`

---

## 8. Deterministic Scoring & Risk Levels

Risk scores are computed transparently via configurable engineering constants:

### Scoring Constants
```python
WEAK_SIGNAL_SCORE = 1.0        # Low-severity or context-required signal
MODERATE_SIGNAL_SCORE = 2.0    # Text prediction or uncorroborated fee
STRONG_SIGNAL_SCORE = 3.0      # Explicit recurring fee, late disclosure, or timer
CORROBORATION_BONUS = 2.0      # Added when >= 2 independent sources corroborate a pattern
MULTI_SOURCE_BONUS = 1.0       # Added when >= 2 distinct sources exist across all evidence
CONFLICT_PENALTY = 1.0         # Subtracted when conflicting evidence is detected
```

### Risk Level Thresholds
- `0.0 <= score <= 2.0`: **`LOW`** (Pure pricing changes, uncorroborated low-risk notices)
- `2.5 <= score <= 4.0`: **`MEDIUM`** (Moderate single-source text or pricing signals)
- `4.5 <= score <= 7.0`: **`HIGH`** (Strong multi-source corroborated risks like subscription traps)
- `score >= 7.5`: **`CRITICAL`** (Aggressive compound risks: trial trap + recurring charges + late fees)

*Note: These thresholds represent an initial engineering baseline and will be calibrated against empirical benchmarks in Phase 9.*

---

## 9. Confidence Calculation

Confidence is not an arbitrary arithmetic average. It reflects evidence quality and provenance:
1. **Base Confidence**: Max confidence among contributing high-severity evidence items (default `0.65`).
2. **Multi-Source Boost**: `+0.15` if cross-source corroboration exists.
3. **Context-Required Penalty**: `-0.15` if `requires_context = true`.
4. **Contradiction Penalty**: `-0.20` if `EvidenceConflict` exists.
5. **Bounds**: Clamped to `[0.10, 0.99]`. If no evidence exists, `confidence = 0.0`.

---

## 10. API Specification: `POST /fuse-evidence`

### Request Schema
```json
{
    "text": "7-day free trial, then ₹999/month."
}
```
*Note: Clients may supply pre-computed `text_prediction`, `price_analysis`, `ui_evidence`, or `behavior_evidence` directly, or provide raw `text` for automated pipeline execution.*

### Response Schema
```json
{
    "source": "evidence_fusion",
    "risk_level": "HIGH",
    "risk_score": 7.0,
    "confidence": 0.89,
    "potential_pattern": "subscription_trap",
    "dark_pattern": "subscription_trap",
    "financial_signal": true,
    "is_corroborated": true,
    "requires_context": false,
    "evidence_groups": [
        {
            "group_id": "G001",
            "pattern": "subscription_risk",
            "evidence_ids": ["E001", "E002", "E003", "E004"],
            "sources": ["text", "price"],
            "corroborated": true,
            "description": "Subscription risk supported by 2 independent sources"
        }
    ],
    "evidence": [
        {
            "evidence_id": "E001",
            "source": "text",
            "type": "subscription_trap",
            "pattern": "subscription_trap",
            "description": "Text predictor identified subscription_trap pattern (confidence: 0.91)",
            "value": 1,
            "confidence": 0.91,
            "severity": "high",
            "provenance": "text_predictor"
        },
        {
            "evidence_id": "E002",
            "source": "price",
            "type": "free_trial",
            "description": "Free trial detected with duration 7 days",
            "value": 0.0,
            "currency": "INR",
            "confidence": 0.95,
            "severity": "medium",
            "provenance": "price_analyzer"
        },
        {
            "evidence_id": "E003",
            "source": "price",
            "type": "renewal_price",
            "description": "Recurring renewal price of 999.0 INR (month)",
            "value": 999.0,
            "currency": "INR",
            "confidence": 0.95,
            "severity": "high",
            "provenance": "price_analyzer"
        }
    ],
    "financial_impact": {
        "trial_price": 0.0,
        "trial_duration_days": 7,
        "renewal_price": 999.0,
        "billing_period": "month",
        "recurring": true
    },
    "consumer_consequence": {
        "type": "recurring_charge",
        "amount": 999.0,
        "currency": "INR",
        "period": "month",
        "description": "Free trial converts to recurring charge of 999.0 INR per month after 7 days"
    },
    "conflicts": []
}
```

---

## 11. Known Limitations & Future Work

1. **DOM / UI and Behavior Analyzers**:
   - The Fusion Engine fully accepts `ui_evidence` and `behavior_evidence` inputs via its schema.
   - Dedicated headless DOM and telemetry extraction modules will be implemented in subsequent phases.
2. **Empirical Threshold Calibration**:
   - Baseline scoring weights (`WEAK`, `MODERATE`, `STRONG`, `BONUS`) are currently rule-based heuristics and will undergo ROC calibration against a labeled multi-modal consumer dataset in Phase 9.
3. **No Unilateral Legal Conclusions**:
   - The engine outputs risk scores and patterns, never legal accusations or definitive liability findings.
