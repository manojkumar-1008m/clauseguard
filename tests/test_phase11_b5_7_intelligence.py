"""tests/test_phase11_b5_7_intelligence.py
Phase B5.7 Intelligence Analysis Layer Test Suite.

Tests:
- Dark Pattern Detector with strict anti-overreach rules
- Consumer Consequence Engine (factual, Decimal-safe, non-legal)
- Historical Change Engine (journey, tab, and product isolated)
- Categories A through T
- Adversarial hard negatives
- Provenance tracing, determinism, and risk score isolation
"""
import pytest
from decimal import Decimal

from backend.schemas.evidence import (
    ContradictionItem,
    EvidenceFusionRequest,
    EvidenceFusionResponse,
    EvidenceItem,
    TemporalRelationshipItem,
)
from backend.schemas.price import DisplayedPrice, PriceAnalysisResponse
from backend.schemas import PredictResponse
from backend.services.evidence_fusion import EvidenceFusionEngine
from backend.services.intelligence_engine import (
    APPROVED_PATTERNS,
    DarkPatternDetector,
    ConsumerConsequenceEngine,
    HistoricalChangeEngine,
    IntelligenceEngine,
    PATTERN_BASKET_SNAKING,
    PATTERN_CONFIRM_SHAMING,
    PATTERN_DRIP_PRICING,
    PATTERN_FALSE_URGENCY,
    PATTERN_FORCED_ACTION,
    PATTERN_MISDIRECTION,
    PATTERN_OBSTRUCTION,
    PATTERN_SCARCITY,
    PATTERN_SUBSCRIPTION_TRAP,
    STATUS_NOT_SUPPORTED,
    STATUS_POTENTIAL,
    STATUS_SUPPORTED,
)
from backend.services.journey_engine import (
    STAGE_CART,
    STAGE_CHECKOUT,
    STAGE_DISCOVERY,
    STAGE_PAYMENT,
    STAGE_PRODUCT,
    STAGE_SUBSCRIPTION,
    STAGE_CANCELLATION,
    STAGE_RETENTION_STEP,
    STAGE_CONFIRMATION,
)


@pytest.fixture
def fusion_engine():
    return EvidenceFusionEngine()


# =============================================================================
# CATEGORY A: SUBSCRIPTION TRAP
# =============================================================================

def test_category_a_subscription_trap_supported():
    """Category A: Free trial + auto renewal + hidden/contradictory renewal price -> SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="free_trial", description="Start your 7-day free trial", decision_context="subscription"),
        EvidenceItem(evidence_id="E2", source="price", type="renewal_price", value=999.0, currency="INR", decision_context="subscription"),
        EvidenceItem(evidence_id="E3", source="dom", type="action_visual_deemphasis", strength="strong", description="Renewal fee hidden in 8px grey text", decision_context="subscription"),
    ]
    pa = PriceAnalysisResponse(renewal_price=999.0, renewal_currency="INR", recurring=True, billing_period="month", trial_duration_days=7)
    assessments = DarkPatternDetector.evaluate(items, [], [], price_analysis=pa)
    sub = next((a for a in assessments if a.pattern == PATTERN_SUBSCRIPTION_TRAP), None)
    assert sub is not None
    assert sub.status == STATUS_SUPPORTED
    assert sub.confidence >= 0.8
    assert "E1" in sub.supporting_evidence_ids


# =============================================================================
# CATEGORY B: LEGITIMATE SUBSCRIPTION
# =============================================================================

def test_category_b_legitimate_subscription_not_supported():
    """Category B: Clear upfront renewal disclosure + easy cancellation -> NOT_SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="subscription_terms", description="Cancel anytime from account settings. Self-serve online.", decision_context="subscription"),
        EvidenceItem(evidence_id="E2", source="price", type="renewal_price", value=499.0, currency="INR", decision_context="subscription"),
    ]
    pa = PriceAnalysisResponse(renewal_price=499.0, renewal_currency="INR", recurring=True, billing_period="month")
    assessments = DarkPatternDetector.evaluate(items, [], [], price_analysis=pa)
    sub = next((a for a in assessments if a.pattern == PATTERN_SUBSCRIPTION_TRAP), None)
    assert sub is not None
    assert sub.status == STATUS_NOT_SUPPORTED
    assert sub.confidence <= 0.3


# =============================================================================
# CATEGORY C: DRIP PRICING
# =============================================================================

def test_category_c_drip_pricing_supported():
    """Category C: Base price ₹499 + previously undisclosed ₹79 fee at checkout -> SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, temporal_position="before_action", journey_stage=STAGE_PRODUCT, decision_context="purchase"),
        EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=79.0, temporal_position="after_action", journey_stage=STAGE_CHECKOUT, decision_context="checkout"),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="fee_added_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="strong",
            reason="Additional processing fee appeared after entering checkout",
        )
    ]
    pa = PriceAnalysisResponse(displayed_price=DisplayedPrice(amount=499.0, currency="INR"), additional_cost=79.0, late_disclosed=True)
    assessments = DarkPatternDetector.evaluate(items, [], temporals, price_analysis=pa)
    drip = next((a for a in assessments if a.pattern == PATTERN_DRIP_PRICING), None)
    assert drip is not None
    assert drip.status == STATUS_SUPPORTED
    assert drip.confidence >= 0.8


# =============================================================================
# CATEGORY D: INCLUSIVE PRICING
# =============================================================================

def test_category_d_inclusive_pricing_not_drip():
    """Category D: ₹499 including all fees declared upfront -> NOT_SUPPORTED (not drip pricing)."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="pricing_transparency", description="All fees included in the displayed ₹499 total", decision_context="purchase"),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=499.0, decision_context="purchase"),
    ]
    pa = PriceAnalysisResponse(displayed_price=DisplayedPrice(amount=499.0, currency="INR"), additional_cost=None, late_disclosed=False)
    assessments = DarkPatternDetector.evaluate(items, [], [], price_analysis=pa)
    drip = next((a for a in assessments if a.pattern == PATTERN_DRIP_PRICING), None)
    # If returned, must be NOT_SUPPORTED
    if drip:
        assert drip.status == STATUS_NOT_SUPPORTED


# =============================================================================
# CATEGORY E: PRICE CHANGE NOT DARK PATTERN
# =============================================================================

def test_category_e_price_change_is_not_automatically_dark_pattern():
    """Category E: Price change 499 -> 599 is factual change, is_dark_pattern must be False."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"product_id": "p100"}),
        EvidenceItem(evidence_id="E2", source="price", type="price_change", value=599.0, journey_id="j1", metadata={"product_id": "p100"}),
    ]
    pa = PriceAnalysisResponse(price_change_detected=True, previous_price=499.0, current_price=599.0, price_change=100.0, price_change_percentage=20.04)
    changes = HistoricalChangeEngine.detect_changes(items, [], price_analysis=pa)
    assert len(changes) >= 1
    p_change = changes[0]
    assert p_change.category == "PRICE_CHANGE"
    assert p_change.previous_value == 499.0
    assert p_change.current_value == 599.0
    assert p_change.absolute_change == 100.0
    assert p_change.is_dark_pattern is False  # Invariant: PRICE_CHANGE != DARK_PATTERN


# =============================================================================
# CATEGORY F: PRODUCT SWITCH NO FALSE PRICE CHANGE
# =============================================================================

def test_category_f_product_switch_no_false_price_change():
    """Category F: Product A ₹499 -> Product B ₹899 browsing does not emit historical price change."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"product_id": "prod_A"}),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=899.0, journey_id="j1", metadata={"product_id": "prod_B"}),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="price_change_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="moderate",
            reason="Different product price viewed",
        )
    ]
    changes = HistoricalChangeEngine.detect_changes(items, temporals, price_analysis=None)
    # Different product IDs prevent cross-product price change
    p_changes = [c for c in changes if c.category == "PRICE_CHANGE"]
    assert len(p_changes) == 0


# =============================================================================
# CATEGORY G: A -> B -> A BROWSING
# =============================================================================

def test_category_g_product_a_b_a_browsing_preserves_journey():
    """Category G: Product A -> Product B -> Product A browsing preserves continuity and does not fragment."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"product_id": "prod_A"}),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=799.0, journey_id="j1", metadata={"product_id": "prod_B"}),
        EvidenceItem(evidence_id="E3", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"product_id": "prod_A"}),
    ]
    res = IntelligenceEngine.analyze(items, [], [])
    # Zero spurious price changes or dark patterns emitted for normal catalog browsing
    p_changes = [c for c in res.historical_changes if c.category == "PRICE_CHANGE"]
    assert len(p_changes) == 0


# =============================================================================
# CATEGORY H: CANCELLATION OBSTRUCTION
# =============================================================================

def test_category_h_cancellation_obstruction_supported():
    """Category H: Multiple retention prompts and loops in cancellation -> SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="behavior", type="repeated_retention_interference", strength="strong", decision_context="cancellation"),
        EvidenceItem(evidence_id="E2", source="dom", type="disabled_action", strength="strong", description="Cancel button disabled during survey", decision_context="cancellation"),
    ]
    contras = [
        ContradictionItem(
            contradiction_id="C1",
            type="dom_vs_behavior",
            source_a="dom",
            source_b="behavior",
            pattern="obstruction",
            severity="strong",
            reason="Cancel action rendered inactive while retention prompts loop",
            evidence_ids=["E1", "E2"],
            decision_context="cancellation",
        )
    ]
    assessments = DarkPatternDetector.evaluate(items, contras, [])
    obs = next((a for a in assessments if a.pattern == PATTERN_OBSTRUCTION), None)
    assert obs is not None
    assert obs.status == STATUS_SUPPORTED
    assert obs.confidence >= 0.85


# =============================================================================
# CATEGORY I: WEAK SIGNAL DOES NOT PRODUCE STRONG PATTERN
# =============================================================================

def test_category_i_weak_signal_does_not_produce_strong_pattern():
    """Category I: Single weak visual disparity does not produce a SUPPORTED pattern."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="action_size_asymmetry", strength="weak", description="Modest 1.2x font disparity", decision_context="dialog"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    assert not any(a.pattern == PATTERN_MISDIRECTION and a.status == STATUS_SUPPORTED for a in assessments)


# =============================================================================
# CATEGORY J: MISSING HISTORY PRESERVES UNKNOWN / NO FABRICATED CHANGE
# =============================================================================

def test_category_j_missing_history_preserves_unknown():
    """Category J: Current price only with no historical snapshot yields no fabricated price change."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=599.0, journey_id="j1"),
    ]
    pa = PriceAnalysisResponse(price_change_detected=True, previous_price=None, current_price=599.0, price_change=None)
    changes = HistoricalChangeEngine.detect_changes(items, [], price_analysis=pa)
    # Current price only without historical evidence item -> no fabricated change
    assert len(changes) == 0

    # Explicit historical snapshot item with missing previous value -> previous_value = "UNKNOWN"
    items_with_snapshot = [
        EvidenceItem(evidence_id="E1", source="price", type="previous_price", value=None, journey_id="j1"),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=599.0, journey_id="j1"),
    ]
    changes2 = HistoricalChangeEngine.detect_changes(items_with_snapshot, [])
    assert len(changes2) == 1
    assert changes2[0].previous_value == "UNKNOWN"
    assert changes2[0].current_value == 599.0
    assert changes2[0].supporting_evidence_ids == ["E1", "E2"]


# =============================================================================
# CATEGORY K: MISSING CONTEXT DOES NOT FABRICATE CONSEQUENCE
# =============================================================================

def test_category_k_missing_context_signals_requires_context():
    """Category K: Evidence with unknown decision context flags requires_context=True and avoids fabricated conclusions."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="additional_cost", value=50.0, decision_context="unknown"),
    ]
    res = IntelligenceEngine.analyze(items, [], [])
    assert res.requires_context is True
    # Verify no fabricated checkout consequence or known financial exposure
    for c in res.consumer_consequences:
        assert "checkout" not in c.consumer_consequence.lower()
        assert c.financial_exposure == "UNKNOWN"


# =============================================================================
# CATEGORY L: CONTRADICTION INTEGRATION
# =============================================================================

def test_category_l_contradiction_integration():
    """Category L: Contradiction 'Cancel anytime' vs disabled button is utilized by intelligence layer."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="cancel_anytime", description="Cancel in one click anytime", decision_context="subscription"),
        EvidenceItem(evidence_id="E2", source="dom", type="disabled_action", description="Cancel button disabled", decision_context="cancellation"),
    ]
    contra = ContradictionItem(
        contradiction_id="C1",
        type="text_vs_dom",
        source_a="text",
        source_b="dom",
        pattern="obstruction",
        severity="strong",
        reason="Promised one-click cancellation contradicted by disabled cancellation button",
        evidence_ids=["E1", "E2"],
        decision_context="cancellation",
    )
    res = IntelligenceEngine.analyze(items, [contra], [])
    obs = next((a for a in res.pattern_assessments if a.pattern == PATTERN_OBSTRUCTION), None)
    assert obs is not None
    assert "E1" in obs.supporting_evidence_ids
    assert "E2" in obs.supporting_evidence_ids


# =============================================================================
# CATEGORY M: TEMPORAL ORDERING GENERATES CONSEQUENCE
# =============================================================================

def test_category_m_temporal_ordering_generates_consequence():
    """Category M: Verified fee addition after action generates incremental cost consequence."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=1000.0, temporal_position="before_action"),
        EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=150.0, temporal_position="after_action"),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="fee_added_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="strong",
            reason="Service fee added at checkout",
        )
    ]
    consequences = ConsumerConsequenceEngine.derive_consequences(items, [], [], temporals)
    assert len(consequences) >= 1
    drip_consequence = next((c for c in consequences if c.type == "additional_fee"), None)
    assert drip_consequence is not None
    assert drip_consequence.actual_cost == 1000.0
    assert drip_consequence.future_cost == 1150.0
    assert drip_consequence.financial_exposure == 150.0


# =============================================================================
# CATEGORY N: NO ORDERING NO TEMPORAL ASSUMPTION
# =============================================================================

def test_category_n_no_ordering_no_temporal_assumption():
    """Category N: Static items without temporal relationship do not assume fee was added later."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, temporal_position="static"),
        EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=50.0, temporal_position="static"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    drip = next((a for a in assessments if a.pattern == PATTERN_DRIP_PRICING), None)
    if drip:
        # Without temporal addition or late disclosure, cannot be SUPPORTED
        assert drip.status != STATUS_SUPPORTED


# =============================================================================
# CATEGORY O: FINANCIAL ISOLATION (UNKNOWN VALUES NEVER GUESSED)
# =============================================================================

def test_category_o_financial_isolation_unknown_never_guessed():
    """Category O: Missing renewal price produces financial_exposure = 'UNKNOWN', never guessed."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="subscription", value=None),
    ]
    pa = PriceAnalysisResponse(recurring=True, renewal_price=None)
    consequences = ConsumerConsequenceEngine.derive_consequences(items, [], [], [], price_analysis=pa)
    assert len(consequences) >= 1
    assert consequences[0].financial_exposure == "UNKNOWN"
    assert consequences[0].renewal_cost is None


# =============================================================================
# CATEGORY P: JOURNEY ISOLATION
# =============================================================================

def test_category_p_journey_isolation_no_cross_journey_comparison():
    """Category P: Prices in Journey A vs Journey B are never compared historically."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j_alpha"),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=599.0, journey_id="j_beta"),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="price_change_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="moderate",
            reason="Different journey prices",
        )
    ]
    changes = HistoricalChangeEngine.detect_changes(items, temporals)
    # Different journey_id values isolate items
    assert len(changes) == 0


# =============================================================================
# CATEGORY Q: TAB ISOLATION
# =============================================================================

def test_category_q_tab_isolation():
    """Category Q: Evidence across Tab 1 and Tab 2 is isolated from historical comparison."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"tab_id": 1, "product_id": "sku1"}),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=599.0, journey_id="j1", metadata={"tab_id": 2, "product_id": "sku1"}),
    ]
    changes = HistoricalChangeEngine.detect_changes(items, [])
    assert len(changes) == 0


# =============================================================================
# CATEGORY R: AUXILIARY ISOLATION
# =============================================================================

def test_category_r_auxiliary_isolation():
    """Category R: Auxiliary evidence (e.g. cookie dialog, terms modal) produces zero commercial dark patterns."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="action_visual_deemphasis", strength="strong", is_auxiliary=True, decision_context="dialog"),
        EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=99.0, is_auxiliary=True, decision_context="dialog"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    assert len(assessments) == 0


# =============================================================================
# CATEGORY S: RISK SCORE ISOLATION
# =============================================================================

def test_category_s_risk_score_isolation(fusion_engine):
    """Category S: B5.7 intelligence confidence does NOT alter B5.2 risk scores or thresholds."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="free_trial", description="7-day free trial", decision_context="subscription"),
        EvidenceItem(evidence_id="E2", source="price", type="renewal_price", value=999.0, currency="INR", decision_context="subscription"),
    ]
    req = EvidenceFusionRequest(raw_evidence=items)
    res = fusion_engine.fuse(req)
    # Risk score remains within B5.2 bounds and intelligence_analysis is populated
    assert res.risk_level == "LOW"
    assert res.risk_score <= 3.0
    assert res.intelligence_analysis is not None
    assert len(res.intelligence_analysis.pattern_assessments) >= 1


# =============================================================================
# CATEGORY T: LLM ISOLATION & DETERMINISM
# =============================================================================

def test_category_t_determinism():
    """Category T: Identical sanitized inputs produce bit-for-bit identical intelligence outputs."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, temporal_position="before_action", journey_id="j1"),
        EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=79.0, temporal_position="after_action", journey_id="j1"),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="fee_added_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="strong",
            reason="Undisclosed booking fee added",
        )
    ]
    res1 = IntelligenceEngine.analyze(items, [], temporals)
    res2 = IntelligenceEngine.analyze(items, [], temporals)

    assert len(res1.pattern_assessments) == len(res2.pattern_assessments)
    assert res1.pattern_assessments[0].pattern == res2.pattern_assessments[0].pattern
    assert res1.pattern_assessments[0].confidence == res2.pattern_assessments[0].confidence
    assert res1.consumer_consequences[0].future_cost == res2.consumer_consequences[0].future_cost


# =============================================================================
# ADVERSARIAL HARD NEGATIVES
# =============================================================================

def test_hard_negative_genuine_countdown():
    """Adversarial: Genuine countdown without artificial resetting is NOT_SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="countdown_timer", description="Sale ends in 4 hours", decision_context="purchase"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    urg = next((a for a in assessments if a.pattern == PATTERN_FALSE_URGENCY), None)
    assert urg is not None
    assert urg.status == STATUS_NOT_SUPPORTED
    assert urg.status != STATUS_SUPPORTED


def test_hard_negative_factual_inventory():
    """Adversarial: '2 colors available' or 'Displays current inventory levels' is NOT deceptive scarcity."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="inventory_statement", description="Displays current inventory levels: 3 variants in stock", decision_context="purchase"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    scarcity = next((a for a in assessments if a.pattern == PATTERN_SCARCITY), None)
    assert scarcity is not None
    assert scarcity.status == STATUS_NOT_SUPPORTED
    assert scarcity.status != STATUS_SUPPORTED


def test_hard_negative_preselected_standard_shipping():
    """Adversarial: Standard shipping default is NOT basket snaking."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="preselected_option", description="Standard Shipping (Free)", element_ref="RADIO_SHIPPING_FREE", decision_context="checkout"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    snaking = next((a for a in assessments if a.pattern == PATTERN_BASKET_SNAKING), None)
    assert snaking is not None
    assert snaking.status == STATUS_NOT_SUPPORTED
    assert snaking.status != STATUS_SUPPORTED


def test_hard_negative_neutral_decline():
    """Adversarial: Neutral decline button ('No thanks') is NOT confirm shaming."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="action_rendered", description="No thanks, skip this step", decision_context="dialog"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    shaming = next((a for a in assessments if a.pattern == PATTERN_CONFIRM_SHAMING), None)
    assert shaming is None


def test_hard_negative_standard_cancellation():
    """Adversarial: Clean 1-step cancellation is NOT obstruction."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="action_rendered", description="Confirm Cancellation", decision_context="cancellation"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    obs = next((a for a in assessments if a.pattern == PATTERN_OBSTRUCTION), None)
    assert obs is None


def test_basket_snaking_commercial_warranty_supported():
    """Positive: Preselected paid warranty add-on is SUPPORTED basket snaking."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="preselected_option", description="2-Year Protection Plan Warranty", value=199.0, element_ref="CHECKBOX_WARRANTY", decision_context="checkout"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    snaking = next((a for a in assessments if a.pattern == PATTERN_BASKET_SNAKING), None)
    assert snaking is not None
    assert snaking.status == STATUS_SUPPORTED
    assert "E1" in snaking.supporting_evidence_ids


def test_confirm_shaming_emotional_guilt_supported():
    """Positive: Emotional guilt decline is SUPPORTED confirm shaming."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="confirm_shaming", description="No thanks, I hate saving money and prefer paying full price", decision_context="dialog"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    shaming = next((a for a in assessments if a.pattern == PATTERN_CONFIRM_SHAMING), None)
    assert shaming is not None
    assert shaming.status == STATUS_SUPPORTED


def test_forced_action_mandatory_survey_supported():
    """Positive: Mandatory survey blocking cancellation is SUPPORTED forced action."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="cancellation_survey", description="Mandatory 10-question cancellation survey before exit", decision_context="cancellation"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    forced = next((a for a in assessments if a.pattern == PATTERN_FORCED_ACTION), None)
    assert forced is not None
    assert forced.status == STATUS_SUPPORTED


def test_provenance_tracing_integrity():
    """Every generated pattern assessment, consequence, and historical change maps to valid evidence IDs."""
    items = [
        EvidenceItem(evidence_id="EV_101", source="text", type="free_trial", description="Free trial converts to recurring", decision_context="subscription"),
        EvidenceItem(evidence_id="EV_102", source="price", type="renewal_price", value=899.0, currency="INR", decision_context="subscription"),
    ]
    pa = PriceAnalysisResponse(renewal_price=899.0, recurring=True, billing_period="month", trial_duration_days=14)
    res = IntelligenceEngine.analyze(items, [], [], price_analysis=pa)

    for p in res.pattern_assessments:
        assert len(p.supporting_evidence_ids) > 0
        for eid in p.supporting_evidence_ids:
            assert eid in ("EV_101", "EV_102")

    for c in res.consumer_consequences:
        assert len(c.supporting_evidence_ids) > 0
        for eid in c.supporting_evidence_ids:
            assert eid in ("EV_101", "EV_102")


# =============================================================================
# P1-01 MANDATORY TESTS: FALSE_URGENCY ANTI-OVERREACH
# =============================================================================

def test_p1_01_strong_countdown_alone_is_not_supported():
    """P1-01: Strong countdown timer alone is NOT_SUPPORTED, never SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="countdown_timer", strength="strong", description="Sale ends in 15 minutes", decision_context="purchase"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    urg = next((a for a in assessments if a.pattern == PATTERN_FALSE_URGENCY), None)
    assert urg is not None
    assert urg.status == STATUS_NOT_SUPPORTED
    assert urg.status != STATUS_SUPPORTED


def test_p1_01_countdown_with_verified_timer_reset_is_supported():
    """P1-01: Countdown + verified timer reset behavior produces SUPPORTED FALSE_URGENCY."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="countdown_timer", description="15:00 minutes remaining", decision_context="purchase"),
        EvidenceItem(evidence_id="E2", source="behavior", type="timer_reset", description="Countdown clock reset to 15:00 upon reload", decision_context="purchase"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    urg = next((a for a in assessments if a.pattern == PATTERN_FALSE_URGENCY), None)
    assert urg is not None
    assert urg.status == STATUS_SUPPORTED
    assert urg.confidence >= 0.8
    assert "E2" in urg.supporting_evidence_ids


def test_p1_01_urgency_text_alone_is_potential_never_supported():
    """P1-01: Promotional urgency text alone produces POTENTIAL, never SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="urgency_text", description="Hurry! Deals ending soon!", decision_context="purchase"),
    ]
    tp = PredictResponse(prediction=1, label="URGENCY", model_version="1.0.0", pattern_category="Urgency", confidence=0.89)
    assessments = DarkPatternDetector.evaluate(items, [], [], text_prediction=tp)
    urg = next((a for a in assessments if a.pattern == PATTERN_FALSE_URGENCY), None)
    assert urg is not None
    assert urg.status in (STATUS_POTENTIAL, STATUS_NOT_SUPPORTED)
    assert urg.status != STATUS_SUPPORTED


def test_p1_01_legitimate_fixed_deadline_is_not_supported():
    """P1-01: Legitimate promotional deadline without reset behavior is NOT_SUPPORTED."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="deadline", description="Offer valid through December 31, 2026", decision_context="purchase"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    urg = next((a for a in assessments if a.pattern == PATTERN_FALSE_URGENCY), None)
    if urg:
        assert urg.status == STATUS_NOT_SUPPORTED
        assert urg.status != STATUS_SUPPORTED


# =============================================================================
# P1-02 MANDATORY TESTS: HISTORICAL CHANGE & PROVENANCE INVARIANTS
# =============================================================================

def test_p1_02_current_price_only_no_fabricated_change():
    """P1-02: Current price only + price_change_detected=True produces NO fabricated change."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=599.0, journey_id="j1"),
    ]
    pa = PriceAnalysisResponse(price_change_detected=True, previous_price=None, current_price=599.0, price_change=None)
    changes = HistoricalChangeEngine.detect_changes(items, [], price_analysis=pa)
    assert len(changes) == 0


def test_p1_02_price_analysis_previous_current_without_evidence_pair_no_fabricated_provenance():
    """P1-02: PriceAnalysis with previous/current prices but no verified evidence pair emits NO change."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=599.0, journey_id="j1"),
    ]
    pa = PriceAnalysisResponse(price_change_detected=True, previous_price=499.0, current_price=599.0, price_change=100.0)
    changes = HistoricalChangeEngine.detect_changes(items, [], price_analysis=pa)
    assert len(changes) == 0
    all_eids = [eid for c in changes for eid in c.supporting_evidence_ids]
    assert "E_PRICE_HISTORICAL" not in all_eids


def test_p1_02_conflicting_product_ids_no_cross_product_price_change():
    """P1-02: Conflicting product IDs never produce a historical price change."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"product_id": "prod_10"}),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=599.0, journey_id="j1", metadata={"product_id": "prod_20"}),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="price_change_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="moderate",
            reason="Price progression across catalog",
        )
    ]
    changes = HistoricalChangeEngine.detect_changes(items, temporals)
    assert len(changes) == 0


def test_p1_02_different_journeys_no_comparison():
    """P1-02: Items across different journeys are isolated from historical comparison."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="journey_A"),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=599.0, journey_id="journey_B"),
    ]
    changes = HistoricalChangeEngine.detect_changes(items, [])
    assert len(changes) == 0


def test_p1_02_different_tabs_no_comparison():
    """P1-02: Items across different tabs are isolated from historical comparison."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"tab_id": 1, "product_id": "p1"}),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=599.0, journey_id="j1", metadata={"tab_id": 2, "product_id": "p1"}),
    ]
    changes = HistoricalChangeEngine.detect_changes(items, [])
    assert len(changes) == 0


def test_p1_02_same_product_journey_verified_temporal_pair_price_change():
    """P1-02: Same product and journey with verified temporal pair correctly produces PRICE_CHANGE."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", metadata={"product_id": "p1"}),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=599.0, journey_id="j1", metadata={"product_id": "p1"}),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="price_change_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="strong",
            reason="Price increased after checkout proceed",
        )
    ]
    changes = HistoricalChangeEngine.detect_changes(items, temporals)
    assert len(changes) == 1
    p = changes[0]
    assert p.category == "PRICE_CHANGE"
    assert p.previous_value == 499.0
    assert p.current_value == 599.0
    assert p.absolute_change == 100.0
    assert p.is_dark_pattern is False
    assert p.supporting_evidence_ids == ["E1", "E2"]


def test_p1_02_all_supporting_evidence_ids_must_exist_in_input_evidence():
    """P1-02: Invariant: every supporting_evidence_id in output must exist in input evidence items."""
    items = [
        EvidenceItem(evidence_id="EV_A", source="text", type="free_trial", description="7-day free trial", decision_context="subscription"),
        EvidenceItem(evidence_id="EV_B", source="price", type="renewal_price", value=999.0, decision_context="subscription"),
        EvidenceItem(evidence_id="EV_C", source="dom", type="action_visual_deemphasis", description="Hidden renewal note", decision_context="subscription"),
    ]
    res = IntelligenceEngine.analyze(items, [], [])
    valid_ids = {"EV_A", "EV_B", "EV_C"}

    for p in res.pattern_assessments:
        for eid in p.supporting_evidence_ids:
            assert eid in valid_ids

    for c in res.consumer_consequences:
        for eid in c.supporting_evidence_ids:
            assert eid in valid_ids

    for h in res.historical_changes:
        for eid in h.supporting_evidence_ids:
            assert eid in valid_ids

    for eid in res.supporting_evidence:
        assert eid in valid_ids


# =============================================================================
# P1-03 MANDATORY TESTS: UNKNOWN CONTEXT SAFETY & CONSEQUENCE BOUNDARIES
# =============================================================================

def test_p1_03_unknown_additional_cost_requires_context_true():
    """P1-03: Additional cost with unknown decision context flags requires_context = True."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="additional_cost", value=79.0, decision_context="unknown"),
    ]
    res = IntelligenceEngine.analyze(items, [], [])
    assert res.requires_context is True


def test_p1_03_unknown_additional_cost_no_supported_drip_pricing():
    """P1-03: Unknown additional cost must NOT produce SUPPORTED DRIP_PRICING."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="additional_cost", value=79.0, decision_context="unknown"),
    ]
    assessments = DarkPatternDetector.evaluate(items, [], [])
    assert not any(a.pattern == PATTERN_DRIP_PRICING and a.status == STATUS_SUPPORTED for a in assessments)
    drip = next((a for a in assessments if a.pattern == PATTERN_DRIP_PRICING), None)
    if drip:
        assert drip.decision_context == "unknown"
        assert "checkout" not in drip.reason.lower()


def test_p1_03_unknown_additional_cost_no_fabricated_checkout_consequence():
    """P1-03: Isolated additional cost with unknown context must not fabricate checkout disclosure claims."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="additional_cost", value=79.0, description="Service fee 79", decision_context="unknown"),
    ]
    consequences = ConsumerConsequenceEngine.derive_consequences(items, [], [], [])
    assert len(consequences) >= 1
    c = consequences[0]
    assert "checkout" not in c.consumer_consequence.lower()
    assert "known total cost increased" not in c.consumer_consequence.lower()
    assert "Service fee 79" in c.consumer_consequence


def test_p1_03_unknown_context_must_not_create_false_financial_consequence():
    """P1-03: Unknown context sets financial_exposure = 'UNKNOWN' and does not fabricate future total."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="additional_cost", value=79.0, decision_context="unknown"),
    ]
    consequences = ConsumerConsequenceEngine.derive_consequences(items, [], [], [])
    assert len(consequences) >= 1
    c = consequences[0]
    assert c.financial_exposure == "UNKNOWN"
    assert c.future_cost is None
    assert c.actual_cost is None


def test_p1_03_unknown_context_plus_explicit_temporal_checkout_becomes_analyzable():
    """P1-03: Unknown context + explicit temporal checkout evidence establishes checkout context."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, temporal_position="before_action", decision_context="unknown"),
        EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=79.0, temporal_position="after_action", decision_context="unknown"),
    ]
    temporals = [
        TemporalRelationshipItem(
            temporal_id="T1",
            type="fee_added_after_action",
            before_evidence_ids=["E1"],
            after_evidence_ids=["E2"],
            strength="strong",
            reason="Mandatory fee added upon proceeding to payment",
        )
    ]
    res = IntelligenceEngine.analyze(items, [], temporals)
    drip = next((a for a in res.pattern_assessments if a.pattern == PATTERN_DRIP_PRICING), None)
    assert drip is not None
    assert drip.status == STATUS_SUPPORTED
    assert drip.decision_context == "checkout"

    fee_c = next((c for c in res.consumer_consequences if c.type == "additional_fee"), None)
    assert fee_c is not None
    assert fee_c.financial_exposure == 79.0
    assert fee_c.future_cost == 578.0
    assert "checkout" in fee_c.consumer_consequence.lower()
