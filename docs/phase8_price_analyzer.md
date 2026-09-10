# ClauseGuard Price & Cost Analyzer (Phases 8.1 – 8.5)

## 1. Overview
The ClauseGuard Price & Cost Analyzer (`backend/services/price_analyzer.py`) provides deterministic, audit-ready extraction and financial relationship analysis of monetary figures, additional fees, discounts, recurring subscriptions, late disclosures, and price changes.

Designed as an independent financial fact engine within ClauseGuard's multi-analyzer architecture, the Price Analyzer produces purely factual financial evidence.

> **Core Principle**: "The Price Analyzer quantifies financial relationships; it does not independently determine whether conduct constitutes a dark pattern or legal violation."

Those evaluations belong strictly to later Evidence Fusion and Risk Engine layers.

---

## 2. Core Capabilities Across Phases

### Phase 8.1 — Monetary Entity Extraction
- **Regex Extraction**: High-precision extraction of prefix (`₹499`, `$29.99`, `€19`, `£49.99`) and suffix (`499 INR`, `999 Rs.`, `29.99 USD`) monetary amounts.
- **Currency Normalization**: Canonical mapping to ISO 4217 currency codes (`₹`/`Rs.`/`INR` $\rightarrow$ `INR`, `$` $\rightarrow$ `USD`, `€` $\rightarrow$ `EUR`, `£` $\rightarrow$ `GBP`).
- **Context & Security**: Sentence-level context extraction without full-page memory dumps; sanitization against credit/debit card numbers ($\ge 13$ continuous digits).

### Phase 8.2 — Cost-Type Classification & Price Relationships
- **Cost Types**: `base_price`, `processing_fee`, `platform_fee`, `service_fee`, `booking_fee`, `convenience_fee`, `shipping_fee`, `delivery_fee`, `handling_fee`, `protection_fee`, `tax`, `add_on`, `other_fee`, `setup_fee`, `discount_amount`, `original_price`, `sale_price`, `total_price`, `trial_price`, `renewal_price`, `subscription_price`, `initial_price`, `previous_price`, `current_price`.
- **Price Relationships**: Semantic linkage metadata including `base_cost`, `additional_cost`, `discount`, `discounted_from`, `original_for_discount`, `final_total`, `alternative`, `trial_offer`, `renews_from`, `recurring_cost`, `price_change_to`, `price_change_from`.

### Phase 8.3 — Cost Calculation & Financial Arithmetic
- **Deterministic Math**: All monetary arithmetic executed using Python `Decimal` quantized to 2 decimal places with `ROUND_HALF_UP`.
- **Explicit-Total Precedence**: If an authoritative stated total is present in the text, it takes precedence over computed subtotals (`explicit_total` vs `calculated_subtotal` vs `known_total`).
- **Safety**: Multi-currency combinations and alternative pricing options are never summed together.
- **Conservative Ambiguity**: Unpriced additional fee notices (e.g. `"+ shipping"`) prevent speculative total calculation.

### Phase 8.4 — Trial, Renewal & Recurring Cost Analysis
- **Recurring Price Detection**: Identifies whether a monetary figure represents an ongoing recurring commitment (`recurring: bool`).
- **Billing Period Normalization**: Normalizes period expressions to canonical tokens: `day`, `week`, `month`, `year`.
- **Trial Extraction**: Extracts trial price (including `free` $\rightarrow$ `0.0`), trial duration in days, and currency.
- **Trial $\rightarrow$ Renewal Linkage**: Links renewal prices to preceding trial offers with `renews_from` and `trial_offer` relationships.
- **Promotional $\rightarrow$ Regular Price Analysis**: Extracts multi-stage promotional subscriptions (e.g. `"First 3 months ₹199, then ₹799/month"`), calculating `price_difference` and `price_change_percentage`.
- **Negative Safeguards**: Rejects non-monetary return periods, warranties, and non-financial renewal actions.

### Phase 8.5 — Late-Disclosure & Price-Change Detection
- **Late-Disclosure Detection**: Deterministically flags cases where a mandatory monetary fee appears after a stated upfront/displayed price (`late_disclosed: true`).
- **Position Tracking**: Preserves character start and end offsets (`character_start`, `character_end`) and original entity ordering (`entity_index`). Tracks `initial_price_position` and `additional_cost_position`.
- **Price-Change Detection**: Detects explicit price transitions (`from X to Y`, `previously X, now Y`, `was X ... now renews at Y`), quantifying `price_change` and `price_change_percentage`.
- **Bidirectional Price Changes**: Supports both price increases (positive values) and price decreases (negative values).
- **Same-Price Guard**: Equal prices (`from ₹999 to ₹999`) result in `price_change = 0.0`, `price_change_detected = false`.
- **Promotional Transitions**: Populates transition metrics on introductory offers without falsely accusing legitimate pricing structures.

---

## 3. Late-Disclosure Detection

### Principles
A late-disclosed fee occurs when an upfront price is presented, followed by a separate, mandatory monetary charge:
1. **Base Price Followed by Fee**:
   - Text: `"Ticket price is ₹499. A processing fee of ₹79 applies."`
   - `displayed_price`: `499.0 INR` (`initial_price_position: 16`)
   - `additional_costs`: `79.0` (`additional_cost_position: 42`)
   - `known_total`: `578.0`
   - `additional_cost_percentage`: `15.83%`
   - `late_disclosed`: `true`
2. **Checkout Surcharges**:
   - Text: `"The product costs ₹999. Shipping ₹120 is added at checkout."`
   - `displayed_price`: `999.0 INR`
   - `additional_costs`: `120.0`
   - `known_total`: `1119.0`
   - `late_disclosed`: `true`
3. **Fee Disclosed Before Base Price**:
   - Text: `"Processing fee ₹79. Ticket price is ₹499."`
   - The fee is disclosed prior to the base price: `late_disclosed: false`.
4. **Unknown / Incomplete Costs**:
   - Text: `"₹499. Taxes and fees apply."` or `"₹499 + shipping"`
   - The fee exists in concept, but has no stated monetary value.
   - `displayed_price`: `499.0 INR`
   - `additional_costs`: `null`, `known_total`: `null`
   - `late_disclosed`: `false` (costs are never guessed or hallucinated).

---

## 4. Price-Change Detection & Arithmetic

### Formulas
All calculations utilize Python `Decimal` quantized to 2 decimal places:
- **Price Change**: $\Delta = \text{current\_price} - \text{previous\_price}$
- **Percentage Change**: $\% = \left(\frac{\text{current\_price} - \text{previous\_price}}{\text{previous\_price}}\right) \times 100$

### Supported Price-Change Forms
1. **Explicit Increase (`from X to Y`)**:
   - Text: `"Price increased from ₹999 to ₹1299."`
   - `previous_price`: `999.0`, `current_price`: `1299.0`
   - `price_change`: `300.0`, `price_change_percentage`: `30.03%`
   - `price_change_detected`: `true`
2. **Explicit Decrease (`reduced from X to Y`)**:
   - Text: `"Price reduced from ₹999 to ₹799."`
   - `previous_price`: `999.0`, `current_price`: `799.0`
   - `price_change`: `-200.0`, `price_change_percentage`: `-20.02%`
   - `price_change_detected`: `true` (negative sign reflects reduction)
3. **Chronological Expressions (`previously X, now Y`)**:
   - Text: `"Previously ₹799, now ₹999."`
   - `previous_price`: `799.0`, `current_price`: `999.0`
   - `price_change`: `200.0`, `price_change_percentage`: `25.03%`
   - `price_change_detected`: `true`
4. **Subscription Renewal Hikes**:
   - Text: `"Renewal price changed from ₹999/month to ₹1,299/month."`
   - `previous_price`: `999.0`, `current_price`: `1299.0`
   - `billing_period`: `"month"`, `recurring`: `true`
   - `price_change`: `300.0`, `price_change_percentage`: `30.03%`
5. **Subscription Transition (`was X ... now renews at Y`)**:
   - Text: `"Your subscription was ₹999/month and now renews at ₹1299/month."`
   - `previous_price`: `999.0`, `current_price`: `1299.0`
   - `billing_period`: `"month"`, `recurring`: `true`
6. **Same Price (`from X to X`)**:
   - Text: `"Price changed from ₹999 to ₹999."`
   - `price_change`: `0.0`, `price_change_percentage`: `0.0%`
   - `price_change_detected`: `false` (not a meaningful price change).

---

## 5. Promotional Transitions & Alternative Pricing Safety

1. **Promotional Intro Rates**:
   - Text: `"₹99 for the first month, then ₹999/month."`
   - `initial_price`: `99.0`, `renewal_price`: `999.0`
   - `price_change`: `900.0`, `price_change_percentage`: `909.09%`
   - `late_disclosed`: `false`
   - Treated strictly as an objective financial transition, not a violation.
2. **Alternative Pricing Isolation**:
   - Text: `"₹99/month or ₹999/year."`
   - Because these are mutually exclusive options, subtraction is forbidden:
   - `is_alternative_pricing`: `true`
   - `price_change`: `null`, `price_change_detected`: `false`
3. **Multi-Currency Safety**:
   - Text: `"₹499 + $20"`
   - Cross-currency combining is strictly rejected. `known_total`: `null`.

---

## 6. Response Schema Reference

```json
{
  "source": "price",
  "entities": [
    {
      "amount": 499.0,
      "currency": "INR",
      "original_text": "₹499",
      "context": "Ticket price is ₹499. A processing fee of ₹79 applies.",
      "type": "base_price",
      "relationship_type": "base_cost",
      "related_entity_index": null,
      "billing_period": null,
      "recurring": false,
      "character_start": 16,
      "character_end": 20,
      "entity_index": 0
    },
    {
      "amount": 79.0,
      "currency": "INR",
      "original_text": "₹79",
      "context": "A processing fee of ₹79 applies.",
      "type": "processing_fee",
      "relationship_type": "additional_cost",
      "related_entity_index": 0,
      "billing_period": null,
      "recurring": false,
      "character_start": 42,
      "character_end": 45,
      "entity_index": 1
    }
  ],
  "displayed_price": {
    "amount": 499.0,
    "currency": "INR"
  },
  "additional_costs": 79.0,
  "additional_cost": 79.0,
  "explicit_total": null,
  "calculated_subtotal": 578.0,
  "known_total": 578.0,
  "total_source": "computed",
  "price_difference": 79.0,
  "additional_cost_percentage": 15.83,
  "discount_amount": null,
  "discount_percentage": null,
  "is_alternative_pricing": false,
  "trial_price": null,
  "trial_currency": null,
  "trial_duration_days": null,
  "initial_price": null,
  "initial_currency": null,
  "later_price": null,
  "renewal_price": null,
  "renewal_currency": null,
  "currency": "INR",
  "billing_period": null,
  "recurring": false,
  "promotion_duration_days": null,
  "promotion_duration_months": null,
  "price_change_percentage": null,
  "previous_price": null,
  "previous_currency": null,
  "current_price": null,
  "current_currency": null,
  "price_change": null,
  "price_change_detected": false,
  "late_disclosed": true,
  "initial_price_position": 16,
  "additional_cost_position": 42
}
```

---

## 7. Limitations & Conservative Handling of Ambiguity

1. **Conservative Inference**: When evidence is incomplete (e.g. `"₹499 + taxes"`), the analyzer never guesses missing numbers. `additional_costs` remains `null`.
2. **Textual Order**: Position indicators rely on deterministic string offsets (`character_start`, `character_end`) and sentence splitting.
3. **Multi-Stage Complexity**: Beyond two-stage pricing structures, the analyzer reports individual price entities conservatively rather than inferring complex multi-tier dependencies.

---

## 8. Architectural Boundaries & Invariants

1. **Zero Dark-Pattern Decisions**: The Price Analyzer strictly refrains from outputting:
   - `dark_pattern`
   - `subscription_trap`
   - `risk_level`
   - `legal_violation`
   - `fraud`
   The service provides audited financial facts only.
2. **TextPredictor Independence**: The V3 Text Predictor (`clauseguard_model_v3.joblib`), `/predict` endpoint, and classification pipelines remain completely untouched and unmodified.
3. **Deterministic Execution**: No LLMs, machine learning models, external network requests, or speculative heuristics are utilized. All operations run in sub-millisecond deterministic regex and Decimal pipelines.

