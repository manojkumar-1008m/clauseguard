# ClauseGuard Consumer Explanation & Action Engine (Phase 8.7)

## 1. Purpose & Core Role
The **ClauseGuard Consumer Explanation & Action Engine** (`backend/services/explanation_engine.py`) operates as the final deterministic translation layer that converts structured evidence from the Evidence Fusion Engine into concise, objective, consumer-friendly explanations, consequences, and practical next steps.

Its primary responsibility is to answer four essential consumer questions:
1. **WHAT happened?** (Headline summary of detected terms)
2. **WHY does it matter?** (Potential consumer consequence)
3. **WHAT could it cost me?** (Quantified financial impact)
4. **WHAT should I check/do next?** (Practical, non-alarming action)

> **Mandatory Architectural Invariant**:
> *"The Explanation Engine transforms existing evidence into consumer-readable language. It does not independently detect risks, establish legal violations, or invent missing facts."*

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
                     ├────────► EVIDENCE FUSION ENGINE ───────► EXPLANATION & ACTION ENGINE ───────► USER-FACING WARNING / UI
PRICE ANALYZER ──────┤          (Phase 8.6)                     (Phase 8.7)
(Phases 8.1 - 8.5)   │          - Cross-source corroboration   - WHAT happened
                     │          - Traceable provenance          - WHY it matters
DOM / UI ANALYZER ───┤          - Conflict handling            - WHAT could it cost
(Future / External)  │          - Anti-double counting          - WHAT you can do
                     │          - Baseline scoring             - Stable evidence IDs
BEHAVIOR ANALYZER ───┘
(Future / External)
```

### Architectural Separation
- **Evidence Fusion**: Combines independent signals, handles duplicates, flags contradictions, and calculates baseline risk scores.
- **Explanation Engine**: Transforms fused evidence into plain, consumer-accessible language and recommended actions. It never classifies text or calculates new prices independently.
- **Risk Engine** (Future): Final regulatory/jurisdictional policy decisioning.

---

## 3. Input Contract & Schema Reference

Defined in `backend/schemas/explanation.py`:

### `ExplanationRequest`
```python
class ExplanationRequest(BaseModel):
    fusion_response: Optional[EvidenceFusionResponse]  # Pre-computed fusion response
    text: Optional[str]                               # Raw text to evaluate end-to-end
    fusion_request: Optional[EvidenceFusionRequest]    # Pre-structured fusion request
```

### `ConsumerExplanationFinding`
Individual findings are ranked and structured as follows:
- `finding_id`: Stable identifier (e.g. `F001`, `F002`)
- `type`: Category (`subscription_risk`, `additional_fee`, `late_disclosure`, `price_change`, `urgency`, `scarcity`, `social_proof`, `misdirection`, `obstruction`, `sneaking`, `forced_action`, `contradiction`, `context_required`, `no_strong_signal`)
- `title`: Primary finding headline (*WHAT WE FOUND*)
- `summary`: Concise statement of facts
- `consumer_consequence`: Consumer consequence (*WHY IT MATTERS*)
- `financial_consequence`: Quantified financial breakdown (*FINANCIAL IMPACT*)
- `recommended_action`: Practical step (*WHAT YOU CAN DO*)
- `evidence_ids`: Contributing atomic `EvidenceItem` identifiers
- `priority`: Priority rank (1 to 6)
- `requires_context`: Boolean flag
- `evidence_summary`: Supporting bullet points

### `ExplanationResponse`
```python
class ExplanationResponse(BaseModel):
    source: str = "consumer_explanation"
    risk_status: str  # 'no_strong_signal', 'risk_detected', 'financial_notice', 'context_required'
    title: str
    summary: str
    evidence_summary: List[str]
    consumer_consequence: Optional[str]
    financial_consequence: Optional[str]
    recommended_action: str
    evidence_ids: List[str]
    pattern: Optional[str]
    requires_context: bool
    confidence: Optional[float]
    disclaimer: Optional[str]
    findings: List[ConsumerExplanationFinding]
    metadata: Dict[str, Any]
```

---

## 4. Prioritization of Multiple Findings

When multiple risks coexist, the engine prioritizes findings using a strict hierarchy:

1. **Priority 1: Direct Financial Increase**: Price increase (`price_change > 0`).
2. **Priority 2: Recurring Commitments & Contradictions**: Subscriptions, free/paid trials to renewals, contradictory pricing terms.
3. **Priority 3: Late Disclosures**: Additional fees appearing after upfront prices.
4. **Priority 4: Stated Mandatory Fees & Sneaking**: Transparent fees, pre-checked add-ons.
5. **Priority 5: UI & Behavioral Manipulation**: Misdirection, friction/obstruction, forced action, urgency with live DOM timers.
6. **Priority 6: Weaker & Informational Signals**: Scarcity, social proof, context-required evaluations, benign baseline.

---

## 5. Explanation Templates & Supported Types

| Finding Type | Input Signal | Headline (*WHAT WE FOUND*) | Consequence (*WHY IT MATTERS*) | Recommended Action (*WHAT YOU CAN DO*) |
|---|---|---|---|---|
| **Free Trial Renewal** | `trial_price=0`, `renewal_price > 0` | Free trial with recurring renewal | After the trial ends, the subscription changes to a recurring charge. | Check the renewal terms and cancellation process before starting the trial. |
| **Paid Trial Renewal** | `trial_price > 0`, `renewal_price > 0` | Paid trial followed by renewal | After the trial, the recurring price increases to the renewal rate. | Check when the renewal begins and how cancellation works. |
| **Additional Fee** | Stated fee without late flag | Additional fee detected | Known total increases to include the additional surcharge. | Review the fee breakdown before payment. |
| **Late Disclosure** | Stated fee with `late_disclosed=True` | Additional cost disclosed later | The final cost increases after the base price was introduced. | Check the final price before confirming the purchase. |
| **Price Increase** | `price_change > 0` | Price changed | Stated price increased from previous quote. | Verify the current price before completing the transaction. |
| **Price Decrease** | `price_change < 0` | Price decreased | You save compared with the earlier quote. | Confirm the discounted price at checkout. |
| **Urgency + Timer** | Urgency text + DOM countdown | Urgency signal detected | Time pressure may encourage committing before reviewing details. | Check whether the offer remains available without the countdown before deciding. |
| **Scarcity** | Low-stock language | Scarcity signal detected | Perceived scarcity may prompt a purchase before comparing options. | Verify stock information before making a rushed decision. |
| **Social Proof** | Purchase count language | Social-proof signal detected | Popularity signals may create a false sense of consensus or urgency. | Evaluate the product independently instead of relying only on popularity signals. |
| **Misdirection** | Visual bias towards higher tier | Misdirection signal detected | Visual emphasis may guide you toward a higher-cost option. | Review all available options carefully, not just the highlighted choice. |
| **Obstruction** | Cancellation friction | Friction in cancellation or choice detected | Unnecessary friction may make canceling or opting out difficult. | Look for account settings, cancellation controls, or support options before committing. |
| **Sneaking** | Pre-selected checkbox | Preselected add-on detected | You may be charged for unwanted extras if not deselected. | Review all selected items before payment. |
| **Forced Action** | Mandatory registration/opt-in | Required step detected | Flow requires an additional action before continuing. | Check whether an alternative path is available. |
| **Context Required** | `requires_context=True` | Additional context needed | Text is insufficient to determine whether it represents a meaningful risk. | Review the surrounding page or checkout flow. |
| **Benign Case** | No significant signals | No strong consumer-risk signal detected | Standard terms without detected high-risk indicators. | Proceed normally and review final checkout totals as standard practice. |

---

## 6. Tone & Legal-Safety Boundaries

### Non-Alarmist Tone
- **Forbidden Phrases**: `"This is illegal"`, `"The company is scamming you"`, `"Fraud detected"`, `"Violating consumer law"`, `"DO NOT BUY!"`.
- **Enforced Tone**: Objective, analytical, practical, and clear.
- **Example**: Instead of `"This site is illegally hiding fees"`, the engine outputs:
  > *"An additional ₹79 fee appears after the initial ₹499 price. Check the final price before confirming the purchase."*

### Compact Disclaimer
For all meaningful risk findings (`risk_status != "no_strong_signal"`), the response includes:
> `"This is a consumer-risk signal, not a legal determination."`

For benign transactions (`no_strong_signal`), no unnecessary legal disclaimer is attached.

---

## 7. Evidence Traceability & Anti-Hallucination

- Every generated sentence strictly maps to extracted values in `FinancialImpact`, `ConsumerConsequence`, or `EvidenceItem`.
- All contributing item IDs (`E001`, `E002`, ...) are linked into both individual findings (`finding.evidence_ids`) and top-level response metadata (`resp.evidence_ids`).
- The engine will **never** invent:
  - Prices or fees
  - Billing cycles or cancellation rules
  - Company names or dates
  - Unobserved UI or DOM behaviors

---

## 8. API Endpoint: `POST /explain`

### Request
```json
{
  "text": "7-day free trial, then ₹999/month."
}
```
*(Optionally accepts pre-computed `fusion_response` or `fusion_request`)*

### Response
```json
{
  "source": "consumer_explanation",
  "risk_status": "financial_notice",
  "title": "Free trial with recurring renewal",
  "summary": "Your 7-day free trial is followed by a ₹999/month recurring charge.",
  "evidence_summary": [
    "7-day free trial",
    "₹999/month renewal",
    "Recurring billing (month)"
  ],
  "consumer_consequence": "After the trial period, the subscription changes to a recurring ₹999 charge per month.",
  "financial_consequence": "Recurring charge of ₹999/month starts after trial.",
  "recommended_action": "Check the renewal terms and cancellation process before starting the trial.",
  "evidence_ids": [
    "E001",
    "E002"
  ],
  "pattern": "subscription_trap",
  "requires_context": false,
  "confidence": 0.95,
  "disclaimer": "This is a consumer-risk signal, not a legal determination.",
  "findings": [
    {
      "finding_id": "F001",
      "type": "subscription_risk",
      "title": "Free trial with recurring renewal",
      "summary": "Your 7-day free trial is followed by a ₹999/month recurring charge.",
      "consumer_consequence": "After the trial period, the subscription changes to a recurring ₹999 charge per month.",
      "financial_consequence": "Recurring charge of ₹999/month starts after trial.",
      "recommended_action": "Check the renewal terms and cancellation process before starting the trial.",
      "evidence_ids": [
        "E001",
        "E002"
      ],
      "pattern": "subscription_trap",
      "priority": 2,
      "requires_context": false,
      "evidence_summary": [
        "7-day free trial",
        "₹999/month renewal",
        "Recurring billing (month)"
      ]
    }
  ],
  "metadata": {
    "total_findings": 1,
    "priority_types": [
      "subscription_risk"
    ],
    "risk_level": "MEDIUM",
    "risk_score": 3.0,
    "is_corroborated": false,
    "conflicts_count": 0
  }
}
```

---

## 9. Known Limitations & Next Steps

1. **Natural Language Variation**: Explanations use deterministic templates to prevent hallucination. Natural language paraphrasing with strict factual constraints may be introduced in a future advisory module.
2. **Context Scope**: Single sentences (e.g. `"Limited-time offer"`) without surrounding page DOM continue to require user verification per `requires_context=True` design principles.
