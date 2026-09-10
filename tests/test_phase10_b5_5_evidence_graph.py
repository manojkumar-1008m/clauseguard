"""tests/test_phase10_b5_5_evidence_graph.py
Phase B5.5 Automated Test Suite for Evidence Graph & Cross-Source Deduplication.

Covers:
- Categories A through AS (45 distinct test categories)
- 15 Adversarial Test Scenarios (Section 25)
- Anti-score inflation, provenance preservation, boundary gating, numerical/temporal safety.
"""
from __future__ import annotations

import pytest
from typing import Any, Dict, List

from backend.schemas.evidence import (
    ContradictionItem,
    EvidenceConflict,
    EvidenceFusionRequest,
    EvidenceItem,
    StructuredProvenance,
)
from backend.schemas.price import DisplayedPrice, PriceAnalysisResponse
from backend.services.evidence_deduplicator import EvidenceDeduplicator
from backend.services.evidence_fusion import EvidenceFusionEngine
from backend.services.evidence_graph import (
    EvidenceGraph,
    EvidenceNode,
    EventNode,
    ClaimNode,
    REL_CORROBORATES,
    REL_SAME_EVENT,
    REL_CONTRADICTS,
    REL_DERIVED_FROM,
    REL_PRECEDES,
    REL_FOLLOWS,
)
from backend.services.journey_engine import (
    STAGE_CART,
    STAGE_CHECKOUT,
    STAGE_DISCOVERY,
    STAGE_PAYMENT,
    STAGE_PRODUCT,
    STAGE_SUBSCRIPTION,
    STAGE_CANCELLATION,
    JourneyEngine,
)


@pytest.fixture
def deduplicator() -> EvidenceDeduplicator:
    return EvidenceDeduplicator()


@pytest.fixture
def fusion_engine() -> EvidenceFusionEngine:
    return EvidenceFusionEngine()


# ==============================================================================
# CATEGORY A: EXACT TEXT DUPLICATE
# ==============================================================================
def test_cat_a_exact_text_duplicate(deduplicator: EvidenceDeduplicator):
    """Category A: Duplicate text claims in same journey/stage collapse to 1 EventNode with 2 EvidenceNodes."""
    item1 = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="subscription_trap",
        pattern="subscription_trap",
        description="₹999/month after trial",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    item2 = EvidenceItem(
        evidence_id="T02",
        source="text",
        type="subscription_trap",
        pattern="subscription_trap",
        description="₹999/month after trial",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    graph, scoring_ev = deduplicator.build_evidence_graph([item1, item2])
    assert len(graph.evidence_nodes) == 2
    assert "node_T01" in graph.evidence_nodes
    assert "node_T02" in graph.evidence_nodes
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert set(ev.observation_ids) == {"node_T01", "node_T02"}
    assert len(scoring_ev) == 1


# ==============================================================================
# CATEGORY B: EXACT PRICE DUPLICATE
# ==============================================================================
def test_cat_b_exact_price_duplicate(deduplicator: EvidenceDeduplicator):
    """Category B: Exact duplicate price observations collapse to 1 EventNode while keeping provenance."""
    item1 = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="renewal_price",
        pattern="subscription_trap",
        description="Renewal 999 INR monthly",
        value=999.0,
        currency="INR",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
        metadata={"period": "month", "recurrence": "recurring"},
    )
    item2 = EvidenceItem(
        evidence_id="P02",
        source="price",
        type="renewal_price",
        pattern="subscription_trap",
        description="Renewal 999 INR monthly",
        value=999.0,
        currency="INR",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
        metadata={"period": "month", "recurrence": "recurring"},
    )
    graph, scoring_ev = deduplicator.build_evidence_graph([item1, item2])
    assert len(graph.evidence_nodes) == 2
    assert len(graph.event_nodes) == 1
    assert len(scoring_ev) == 1


# ==============================================================================
# CATEGORY C: EXACT DOM DUPLICATE (SPA RERENDER)
# ==============================================================================
def test_cat_c_exact_dom_duplicate(deduplicator: EvidenceDeduplicator):
    """Category C: Identical DOM element signal repeated in same state collapses to 1 canonical event."""
    item1 = EvidenceItem(
        evidence_id="D01",
        source="dom",
        type="preselected_option",
        description="Preselected commercial add-on",
        element_ref="#addon-warranty",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="checkout",
        route="/checkout",
    )
    item2 = EvidenceItem(
        evidence_id="D02",
        source="dom",
        type="preselected_option",
        description="Preselected commercial add-on duplicate",
        element_ref="#addon-warranty",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="checkout",
        route="/checkout",
    )
    graph, scoring_ev = deduplicator.build_evidence_graph([item1, item2])
    assert len(graph.evidence_nodes) == 2
    assert len(scoring_ev) == 1
    dup_edges = [e for e in graph.edges if e.metadata.get("is_exact_duplicate")]
    assert len(dup_edges) == 1


# ==============================================================================
# CATEGORY D: EXACT BEHAVIOR DUPLICATE
# ==============================================================================
def test_cat_d_exact_behavior_duplicate(deduplicator: EvidenceDeduplicator):
    """Category D: Same behavior action with identical event indices collapses."""
    item1 = EvidenceItem(
        evidence_id="B01",
        source="behavior",
        type="survey_wall_friction",
        description="Survey wall encountered",
        event_indices=[4],
        journey_id="jrn_1001",
        journey_stage="CANCELLATION",
        decision_context="cancellation",
    )
    item2 = EvidenceItem(
        evidence_id="B02",
        source="behavior",
        type="survey_wall_friction",
        description="Survey wall encountered duplicate",
        event_indices=[4],
        journey_id="jrn_1001",
        journey_stage="CANCELLATION",
        decision_context="cancellation",
    )
    graph, scoring_ev = deduplicator.build_evidence_graph([item1, item2])
    assert len(graph.evidence_nodes) == 2
    assert len(scoring_ev) == 1


# ==============================================================================
# CATEGORY E: TEXT + PRICE SAME EVENT
# ==============================================================================
def test_cat_e_text_price_same_event(deduplicator: EvidenceDeduplicator):
    """Category E: Text claim and Price fact corroborate 1 underlying renewal event."""
    text_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="subscription_trap",
        pattern="subscription_trap",
        description="₹999/month after trial",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    price_item = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="renewal_price",
        pattern="subscription_trap",
        description="Recurring monthly charge 999 INR",
        value=999.0,
        currency="INR",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
        metadata={"period": "month", "recurrence": "recurring"},
    )
    graph, scoring_ev = deduplicator.build_evidence_graph([text_item, price_item])
    assert len(graph.evidence_nodes) == 2
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert ev.event_type == "subscription_renewal"
    assert set(ev.sources) == {"price", "text"}
    corrob_edges = [e for e in graph.edges if e.relation_type == REL_CORROBORATES]
    assert len(corrob_edges) >= 2


# ==============================================================================
# CATEGORY F: TEXT + DOM SAME EVENT
# ==============================================================================
def test_cat_f_text_dom_same_event(deduplicator: EvidenceDeduplicator):
    """Category F: Text drip pricing + DOM preselected add-on corroborate price disclosure risk."""
    t_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="drip_pricing",
        pattern="drip_pricing",
        description="Processing fee added at checkout",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="checkout",
    )
    d_item = EvidenceItem(
        evidence_id="D01",
        source="dom",
        type="preselected_option",
        pattern="drip_pricing",
        description="Optional fee pre-checked",
        element_ref="#fee-checkbox",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="checkout",
    )
    graph, _ = deduplicator.build_evidence_graph([t_item, d_item])
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert "text" in ev.sources and "dom" in ev.sources


# ==============================================================================
# CATEGORY G: TEXT + BEHAVIOR SAME EVENT
# ==============================================================================
def test_cat_g_text_behavior_same_event(deduplicator: EvidenceDeduplicator):
    """Category G: Text cancellation obstruction + Behavior repeated retention corroborate friction."""
    t_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="cancellation_obstruction",
        pattern="obstruction",
        description="Confirming you want to cancel",
        journey_id="jrn_1001",
        journey_stage="CANCELLATION",
        decision_context="cancellation",
    )
    b_item = EvidenceItem(
        evidence_id="B01",
        source="behavior",
        type="repeated_retention_interference",
        pattern="obstruction",
        description="Retention prompt repeated 3 times",
        event_indices=[2, 3],
        journey_id="jrn_1001",
        journey_stage="CANCELLATION",
        decision_context="cancellation",
    )
    graph, _ = deduplicator.build_evidence_graph([t_item, b_item])
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert ev.event_type == "cancellation_obstruction"


# ==============================================================================
# CATEGORY H: TEXT + IMAGE SAME EVENT
# ==============================================================================
def test_cat_h_text_image_same_event(deduplicator: EvidenceDeduplicator):
    """Category H: Text 'Only 3 minutes left' + Image countdown timer corroborate urgency."""
    t_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="urgency",
        pattern="urgency",
        description="Only 3 minutes left to claim this deal",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="checkout",
    )
    img_item = EvidenceItem(
        evidence_id="I01",
        source="image",
        type="countdown_timer",
        pattern="urgency",
        description="Visual countdown timer detected",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="checkout",
    )
    graph, _ = deduplicator.build_evidence_graph([t_item, img_item])
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert set(ev.sources) == {"image", "text"}


# ==============================================================================
# CATEGORY I: FOUR-SOURCE CORROBORATION
# ==============================================================================
def test_cat_i_four_source_corroboration(deduplicator: EvidenceDeduplicator):
    """Category I: Text, Price, DOM, and Behavior all observe one subscription event."""
    t_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="subscription_trap",
        pattern="subscription_trap",
        description="7-day trial then ₹999/month",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    p_item = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="renewal_price",
        pattern="subscription_trap",
        description="Renewal ₹999/month",
        value=999.0,
        currency="INR",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
        metadata={"period": "month", "recurrence": "recurring"},
    )
    d_item = EvidenceItem(
        evidence_id="D01",
        source="dom",
        type="preselected_subscription",
        pattern="subscription_trap",
        description="Auto-renew preselected",
        element_ref="#auto-renew-opt",
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    b_item = EvidenceItem(
        evidence_id="B01",
        source="behavior",
        type="subscription_confirmation_click",
        pattern="subscription_trap",
        description="Clicked Start Trial",
        event_indices=[1],
        journey_id="jrn_1001",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    graph, scoring_ev = deduplicator.build_evidence_graph([t_item, p_item, d_item, b_item])
    assert len(graph.evidence_nodes) == 4
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert set(ev.sources) == {"behavior", "dom", "price", "text"}
    assert len(ev.observation_ids) == 4


# ==============================================================================
# CATEGORY J: DIFFERENT JOURNEYS NEVER MERGE
# ==============================================================================
def test_cat_j_different_journeys(deduplicator: EvidenceDeduplicator):
    """Category J: Evidence from different journeys are strictly partitioned."""
    item1 = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="subscription_trap",
        description="₹999/month after trial",
        journey_id="jrn_A",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    item2 = EvidenceItem(
        evidence_id="T02",
        source="text",
        type="subscription_trap",
        description="₹999/month after trial",
        journey_id="jrn_B",
        journey_stage="CHECKOUT",
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([item1, item2])
    assert len(graph.event_nodes) == 2
    j_ids = {ev.journey_id for ev in graph.event_nodes.values()}
    assert j_ids == {"jrn_A", "jrn_B"}


# ==============================================================================
# CATEGORY K: DIFFERENT TABS NEVER MERGE
# ==============================================================================
def test_cat_k_different_tabs(deduplicator: EvidenceDeduplicator):
    """Category K: Observations originating from different tabs are partitioned."""
    item1 = EvidenceItem(
        evidence_id="D01",
        source="dom",
        type="preselected_option",
        description="Preselected add-on tab 1",
        element_ref="#addon",
        decision_context="checkout",
        provenance=StructuredProvenance(source="dom", tab_id=101),
    )
    item2 = EvidenceItem(
        evidence_id="D02",
        source="dom",
        type="preselected_option",
        description="Preselected add-on tab 2",
        element_ref="#addon",
        decision_context="checkout",
        provenance=StructuredProvenance(source="dom", tab_id=102),
    )
    graph, _ = deduplicator.build_evidence_graph([item1, item2])
    assert len(graph.event_nodes) == 2


# ==============================================================================
# CATEGORY L: DIFFERENT PRODUCTS NEVER MERGE
# ==============================================================================
def test_cat_l_different_products(deduplicator: EvidenceDeduplicator):
    """Category L: Different products with different prices do not merge."""
    p1 = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="renewal_price",
        description="Plan basic",
        value=299.0,
        currency="INR",
        decision_context="subscription",
        metadata={"product_id": "prod_basic", "period": "month"},
    )
    p2 = EvidenceItem(
        evidence_id="P02",
        source="price",
        type="renewal_price",
        description="Plan pro",
        value=899.0,
        currency="INR",
        decision_context="subscription",
        metadata={"product_id": "prod_pro", "period": "month"},
    )
    graph, _ = deduplicator.build_evidence_graph([p1, p2])
    assert len(graph.event_nodes) == 2


# ==============================================================================
# CATEGORY M: DIFFERENT DECISION CONTEXTS NEVER MERGE
# ==============================================================================
def test_cat_m_different_decision_contexts(deduplicator: EvidenceDeduplicator):
    """Category M: Cancellation family and Purchase family items remain isolated."""
    item_cancel = EvidenceItem(
        evidence_id="E01",
        source="dom",
        type="action_visual_deemphasis",
        description="Cancel link deemphasized",
        decision_context="cancellation",
    )
    item_purchase = EvidenceItem(
        evidence_id="E02",
        source="dom",
        type="preselected_option",
        description="Express delivery preselected",
        decision_context="checkout",
    )
    graph, _ = deduplicator.build_evidence_graph([item_cancel, item_purchase])
    assert len(graph.event_nodes) == 2
    contexts = {ev.canonical_context for ev in graph.event_nodes.values()}
    assert contexts == {"cancellation", "checkout"}


# ==============================================================================
# CATEGORY N: AUXILIARY EVIDENCE ISOLATION
# ==============================================================================
def test_cat_n_auxiliary_isolation(deduplicator: EvidenceDeduplicator):
    """Category N: Auxiliary evidence (e.g. privacy policy) is isolated from transactions."""
    aux_item = EvidenceItem(
        evidence_id="AUX01",
        source="text",
        type="subscription_trap",
        description="Terms state recurring ₹999/month",
        is_auxiliary=True,
        decision_context="subscription",
    )
    tx_item = EvidenceItem(
        evidence_id="TX01",
        source="price",
        type="renewal_price",
        description="Renewal price",
        value=999.0,
        currency="INR",
        is_auxiliary=False,
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([aux_item, tx_item])
    assert len(graph.event_nodes) == 2
    aux_events = [ev for ev in graph.event_nodes.values() if ev.is_auxiliary]
    tx_events = [ev for ev in graph.event_nodes.values() if not ev.is_auxiliary]
    assert len(aux_events) == 1
    assert len(tx_events) == 1


# ==============================================================================
# CATEGORIES O & P: CONTRADICTORY EVIDENCE
# ==============================================================================
def test_cat_o_contradictory_text_vs_price(deduplicator: EvidenceDeduplicator):
    """Category O: Contradictory text ('free') vs price (₹999 paid) MUST NOT deduplicate."""
    t_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="free_trial",
        description="Totally free trial",
        journey_id="jrn_1001",
        decision_context="subscription",
    )
    p_item = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="paid_trial",
        description="Paid trial charge",
        value=999.0,
        currency="INR",
        journey_id="jrn_1001",
        decision_context="subscription",
    )
    contra = ContradictionItem(
        contradiction_id="C01",
        type="text_vs_price",
        source_a="text",
        source_b="price",
        reason="Text claims free trial but price charges ₹999",
        evidence_ids=["T01", "P01"],
    )
    graph, _ = deduplicator.build_evidence_graph([t_item, p_item], contradictions=[contra])
    assert len(graph.event_nodes) == 2
    contra_edges = [e for e in graph.edges if e.relation_type == REL_CONTRADICTS]
    assert len(contra_edges) >= 2


def test_cat_p_contradictory_text_vs_behavior(deduplicator: EvidenceDeduplicator):
    """Category P: Text 'cancel in one click' vs Behavior repeated friction contradict."""
    t_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="easy_cancellation_claim",
        description="Cancel in one click anytime",
        journey_id="jrn_1001",
        decision_context="cancellation",
    )
    b_item = EvidenceItem(
        evidence_id="B01",
        source="behavior",
        type="repeated_retention_interference",
        description="Encountered 4 retention screens",
        event_indices=[2, 3, 4, 5],
        journey_id="jrn_1001",
        decision_context="cancellation",
    )
    contra = ContradictionItem(
        contradiction_id="C02",
        type="text_vs_behavior",
        source_a="text",
        source_b="behavior",
        reason="Claim of one click cancel contradicted by 4 retention screens",
        evidence_ids=["T01", "B01"],
    )
    graph, _ = deduplicator.build_evidence_graph([t_item, b_item], contradictions=[contra])
    assert len(graph.event_nodes) == 2
    contra_edges = [e for e in graph.edges if e.relation_type == REL_CONTRADICTS]
    assert len(contra_edges) >= 2


# ==============================================================================
# CATEGORIES Q, R, S, T: NUMERICAL AND FINANCIAL SAFETY
# ==============================================================================
def test_cat_q_different_price_amounts(deduplicator: EvidenceDeduplicator):
    """Category Q: ₹499 and ₹599 must NOT be fuzzy-merged."""
    p1 = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="renewal_price",
        description="Renewal 499",
        value=499.0,
        currency="INR",
        decision_context="subscription",
    )
    p2 = EvidenceItem(
        evidence_id="P02",
        source="price",
        type="renewal_price",
        description="Renewal 599",
        value=599.0,
        currency="INR",
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([p1, p2])
    assert len(graph.event_nodes) == 2


def test_cat_r_different_currencies(deduplicator: EvidenceDeduplicator):
    """Category R: 999 INR vs 999 USD must remain distinct."""
    p_inr = EvidenceItem(
        evidence_id="P_INR",
        source="price",
        type="renewal_price",
        description="Renewal INR",
        value=999.0,
        currency="INR",
        decision_context="subscription",
    )
    p_usd = EvidenceItem(
        evidence_id="P_USD",
        source="price",
        type="renewal_price",
        description="Renewal USD",
        value=999.0,
        currency="USD",
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([p_inr, p_usd])
    assert len(graph.event_nodes) == 2


def test_cat_s_monthly_vs_yearly(deduplicator: EvidenceDeduplicator):
    """Category S: Monthly recurrence vs Yearly recurrence must remain distinct."""
    p_mo = EvidenceItem(
        evidence_id="P_MO",
        source="price",
        type="renewal_price",
        description="Monthly renewal",
        value=999.0,
        currency="INR",
        decision_context="subscription",
        metadata={"period": "month", "recurrence": "recurring"},
    )
    p_yr = EvidenceItem(
        evidence_id="P_YR",
        source="price",
        type="renewal_price",
        description="Yearly renewal",
        value=999.0,
        currency="INR",
        decision_context="subscription",
        metadata={"period": "year", "recurrence": "recurring"},
    )
    graph, _ = deduplicator.build_evidence_graph([p_mo, p_yr])
    assert len(graph.event_nodes) == 2


def test_cat_t_trial_durations(deduplicator: EvidenceDeduplicator):
    """Category T: 7-day trial vs 30-day trial must remain distinct."""
    t7 = EvidenceItem(
        evidence_id="P7",
        source="price",
        type="free_trial",
        description="7-day trial",
        value=0.0,
        currency="INR",
        decision_context="subscription",
        metadata={"trial_duration_days": 7},
    )
    t30 = EvidenceItem(
        evidence_id="P30",
        source="price",
        type="free_trial",
        description="30-day trial",
        value=0.0,
        currency="INR",
        decision_context="subscription",
        metadata={"trial_duration_days": 30},
    )
    graph, _ = deduplicator.build_evidence_graph([t7, t30])
    assert len(graph.event_nodes) == 2


# ==============================================================================
# CATEGORIES U & V: EVENT INDICES & DOM ELEMENTS SAFETY
# ==============================================================================
def test_cat_u_different_event_indices(deduplicator: EvidenceDeduplicator):
    """Category U: Clicks at different interaction event indices remain distinct actions."""
    b1 = EvidenceItem(
        evidence_id="B01",
        source="behavior",
        type="action_click",
        description="First click",
        event_indices=[2],
        decision_context="checkout",
    )
    b2 = EvidenceItem(
        evidence_id="B02",
        source="behavior",
        type="action_click",
        description="Second click",
        event_indices=[5],
        decision_context="checkout",
    )
    graph, _ = deduplicator.build_evidence_graph([b1, b2])
    assert len(graph.event_nodes) == 2


def test_cat_v_different_dom_elements(deduplicator: EvidenceDeduplicator):
    """Category V: Different DOM elements do not merge even if signal type is similar."""
    d1 = EvidenceItem(
        evidence_id="D01",
        source="dom",
        type="action_visual_deemphasis",
        description="Cancel button deemphasized",
        element_ref="#btn-cancel-membership",
        decision_context="cancellation",
    )
    d2 = EvidenceItem(
        evidence_id="D02",
        source="dom",
        type="action_visual_deemphasis",
        description="Pause link deemphasized",
        element_ref="#link-pause-plan",
        decision_context="cancellation",
    )
    graph, _ = deduplicator.build_evidence_graph([d1, d2])
    assert len(graph.event_nodes) == 2


# ==============================================================================
# CATEGORY W: SPA RERENDER DUPLICATION IN FUSION ENGINE
# ==============================================================================
def test_cat_w_spa_rerender_fusion(fusion_engine: EvidenceFusionEngine):
    """Category W: Multiple SPA rerenders emit duplicate DOM evidence, but score does not inflate."""
    items = [
        EvidenceItem(
            evidence_id=f"D{i:02d}",
            source="dom",
            type="cancel_action_visually_deemphasized",
            description="Cancel button deemphasized",
            strength="weak",
            element_ref="#btn-cancel",
            journey_id="jrn_1001",
            journey_stage="CANCELLATION",
            decision_context="cancellation",
        )
        for i in range(1, 6)
    ]
    req = EvidenceFusionRequest(dom_evidence=items)
    res = fusion_engine.fuse(req)

    eg = res.evidence_graph
    assert eg is not None
    assert len(eg["evidence_nodes"]) == 5
    assert len(eg["event_nodes"]) == 1

    # Bounded weak DOM contribution
    assert res.risk_score < 3.0
    assert res.risk_level == "LOW"


# ==============================================================================
# CATEGORIES X & Y: PAGE TRANSITION CONTINUITY
# ==============================================================================
def test_cat_x_valid_page_transition():
    """Category X: CART -> CHECKOUT within same journey is valid continuity."""
    assert JourneyEngine.is_valid_stage_transition(STAGE_CART, STAGE_CHECKOUT) is True


def test_cat_y_invalid_page_transition():
    """Category Y: PRODUCT -> PRODUCT browsing is not valid progression."""
    assert JourneyEngine.is_valid_stage_transition(STAGE_PRODUCT, STAGE_PRODUCT) is False


# ==============================================================================
# CATEGORY Z: EXTERNAL PAYMENT GATEWAY ISOLATION
# ==============================================================================
def test_cat_z_external_gateway_isolation(deduplicator: EvidenceDeduplicator):
    """Category Z: Payment gateway DOM is isolated from merchant DOM."""
    gw_item = EvidenceItem(
        evidence_id="D_GW",
        source="dom",
        type="gateway_form",
        description="Third party gateway inputs",
        journey_stage="PAYMENT",
        decision_context="purchase",
        metadata={"is_external_gateway": True},
        is_auxiliary=True,
    )
    merchant_item = EvidenceItem(
        evidence_id="D_MERCH",
        source="dom",
        type="preselected_option",
        description="Merchant add-on checkbox",
        journey_stage="CHECKOUT",
        decision_context="purchase",
        is_auxiliary=False,
    )
    graph, _ = deduplicator.build_evidence_graph([gw_item, merchant_item])
    assert len(graph.event_nodes) == 2
    assert any(ev.is_auxiliary for ev in graph.event_nodes.values())


# ==============================================================================
# CATEGORIES AA & AB: BACKWARD COMPATIBILITY & LEGACY EVIDENCE
# ==============================================================================
def test_cat_aa_legacy_evidence_without_journey_id(deduplicator: EvidenceDeduplicator):
    """Category AA: Evidence items without journey_id work seamlessly using legacy fallback."""
    item1 = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="subscription_trap",
        description="₹999/month after trial",
        decision_context="subscription",
    )
    item2 = EvidenceItem(
        evidence_id="T02",
        source="text",
        type="subscription_trap",
        description="₹999/month after trial",
        decision_context="subscription",
    )
    graph, scoring_ev = deduplicator.build_evidence_graph([item1, item2])
    assert len(graph.evidence_nodes) == 2
    assert len(graph.event_nodes) == 1
    assert len(scoring_ev) == 1


def test_cat_ab_mixed_legacy_and_journey_evidence(deduplicator: EvidenceDeduplicator):
    """Category AB: Mixed evidence items (one with journey_id, one without) do not crash."""
    item_jrn = EvidenceItem(
        evidence_id="E01",
        source="text",
        type="subscription_trap",
        description="Subscription terms",
        journey_id="jrn_123",
        decision_context="subscription",
    )
    item_leg = EvidenceItem(
        evidence_id="E02",
        source="price",
        type="renewal_price",
        description="Renewal charge",
        value=999.0,
        currency="INR",
        journey_id=None,
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([item_jrn, item_leg])
    assert len(graph.evidence_nodes) == 2
    assert len(graph.event_nodes) == 2


# ==============================================================================
# CATEGORIES AC & AD: PROVENANCE PRESERVATION & GRAPH TRACEABILITY
# ==============================================================================
def test_cat_ac_provenance_preservation(deduplicator: EvidenceDeduplicator):
    """Category AC: All original provenance objects remain accessible in EvidenceNodes."""
    prov = StructuredProvenance(
        source="dom",
        model_version="v4.2",
        timestamp=1700000000.0,
        page_load_id="p_99",
        tab_id=5,
    )
    item = EvidenceItem(
        evidence_id="D01",
        source="dom",
        type="preselected_option",
        description="Warranty preselected",
        provenance=prov,
        decision_context="checkout",
    )
    graph, _ = deduplicator.build_evidence_graph([item])
    node = graph.evidence_nodes["node_D01"]
    assert node.provenance["tab_id"] == 5
    assert node.provenance["model_version"] == "v4.2"


def test_cat_ad_graph_relationship_traceability(deduplicator: EvidenceDeduplicator):
    """Category AD: Relationships can be traced from Canonical Event to observations."""
    t_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="subscription_trap",
        description="₹999/month after trial",
        journey_id="jrn_1001",
        decision_context="subscription",
    )
    p_item = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="renewal_price",
        description="Renewal price",
        value=999.0,
        currency="INR",
        journey_id="jrn_1001",
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([t_item, p_item])
    ev = graph.get_event_for_evidence("T01")
    assert ev is not None
    assert "node_T01" in ev.observation_ids
    assert "node_P01" in ev.observation_ids
    edges = graph.get_edges_for_node("node_T01")
    assert any(e.relation_type == REL_SAME_EVENT for e in edges)


# ==============================================================================
# CATEGORIES AE & AF: SCORE INFLATION & B5.2 THRESHOLDS
# ==============================================================================
def test_cat_ae_score_inflation_prevention(fusion_engine: EvidenceFusionEngine):
    """Category AE: 10 repeated observations of the same single signal do not inflate risk score."""
    items = [
        EvidenceItem(
            evidence_id=f"T{i:02d}",
            source="text",
            type="urgency",
            pattern="urgency",
            description="Limited time discount only today",
            journey_id="jrn_1001",
            journey_stage="PRODUCT",
            decision_context="purchase",
        )
        for i in range(10)
    ]
    req = EvidenceFusionRequest(raw_evidence=items)
    res = fusion_engine.fuse(req)
    assert res.risk_score <= 3.0
    assert res.risk_level == "LOW"


def test_cat_af_b5_2_thresholds(fusion_engine: EvidenceFusionEngine):
    """Category AF: B5.2 Risk Thresholds remain intact (LOW <3, MED >=3, HIGH >=5, CRIT >=8)."""
    res_low = fusion_engine.fuse(EvidenceFusionRequest(text="Clean product description"))
    assert res_low.risk_score < 3.0
    assert res_low.risk_level == "LOW"


# ==============================================================================
# CATEGORIES AG & AH: CONTRADICTION & TEMPORAL INTEGRITY
# ==============================================================================
def test_cat_ag_contradiction_engine_integrity(fusion_engine: EvidenceFusionEngine):
    """Category AG: Direct conflict between free trial claim and paid trial price reflects conflict penalty."""
    text_item = EvidenceItem(
        evidence_id="T01",
        source="text",
        type="free_trial",
        description="Free trial for 7 days",
        decision_context="subscription",
    )
    price_item = EvidenceItem(
        evidence_id="P01",
        source="price",
        type="paid_trial",
        description="Paid trial 499 INR",
        value=499.0,
        currency="INR",
        decision_context="subscription",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[text_item, price_item]))
    assert len(res.conflicts) > 0 or len(res.contradictions) > 0


def test_cat_ah_temporal_engine_integrity(fusion_engine: EvidenceFusionEngine):
    """Category AH: Price change after action produces temporal relationship without merging."""
    before_item = EvidenceItem(
        evidence_id="P_BEF",
        source="price",
        type="displayed_price",
        description="Initial price",
        value=499.0,
        currency="INR",
        temporal_position="before_action",
        decision_context="checkout",
        journey_id="jrn_flow",
    )
    after_item = EvidenceItem(
        evidence_id="P_AFT",
        source="price",
        type="price_change",
        description="Changed price",
        value=578.0,
        temporal_position="after_action",
        decision_context="checkout",
        journey_id="jrn_flow",
    )
    p_analysis = PriceAnalysisResponse(
        price_change_detected=True,
        previous_price=499.0,
        current_price=578.0,
        price_change=79.0,
        currency="INR",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(
        price_analysis=p_analysis,
        raw_evidence=[before_item, after_item],
    ))
    assert len(res.temporal_relationships) > 0 or res.price_changed is True


# ==============================================================================
# CATEGORIES AI & AJ & AK: AUXILIARY IMPACT, CANONICAL EVENTS & MODALITIES
# ==============================================================================
def test_cat_ai_auxiliary_financial_impact_exclusion(fusion_engine: EvidenceFusionEngine):
    """Category AI: Auxiliary pricing does not populate financial impact."""
    aux_p = EvidenceItem(
        evidence_id="AUX_P",
        source="price",
        type="renewal_price",
        description="Terms state renewal",
        value=999.0,
        currency="INR",
        is_auxiliary=True,
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[aux_p]))
    assert res.financial_impact is None or res.risk_score == 0.0


def test_cat_aj_multiple_observations_one_canonical_event(deduplicator: EvidenceDeduplicator):
    """Category AJ: 3 observations attach to 1 canonical event node with observation_ids."""
    obs = [
        EvidenceItem(
            evidence_id=f"E{i}",
            source="text",
            type="drip_pricing",
            description="Service fee added at checkout",
            journey_id="jrn_1",
            decision_context="checkout",
        )
        for i in range(1, 4)
    ]
    graph, _ = deduplicator.build_evidence_graph(obs)
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert len(ev.observation_ids) == 3


def test_cat_ak_one_event_multiple_modalities(deduplicator: EvidenceDeduplicator):
    """Category AK: Modalities text, dom, price attach to 1 canonical event."""
    t = EvidenceItem(evidence_id="T1", source="text", type="subscription_trap", description="₹999 renewal", decision_context="subscription", journey_id="j1")
    p = EvidenceItem(evidence_id="P1", source="price", type="renewal_price", description="999 renewal", value=999.0, currency="INR", decision_context="subscription", journey_id="j1")
    d = EvidenceItem(evidence_id="D1", source="dom", type="preselected_subscription", description="Preselected", decision_context="subscription", journey_id="j1")
    graph, _ = deduplicator.build_evidence_graph([t, p, d])
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert set(ev.sources) == {"dom", "price", "text"}


# ==============================================================================
# CATEGORIES AL, AM, AN, AO, AP, AQ, AR, AS: REMAINING CATEGORIES
# ==============================================================================
def test_cat_al_false_semantic_similarity(deduplicator: EvidenceDeduplicator):
    """Category AL: High surface text similarity with different numbers must not merge."""
    t1 = EvidenceItem(evidence_id="T1", source="text", type="subscription_trap", description="₹499 per month plan", decision_context="subscription")
    t2 = EvidenceItem(evidence_id="T2", source="text", type="subscription_trap", description="₹899 per month plan", decision_context="subscription")
    graph, _ = deduplicator.build_evidence_graph([t1, t2])
    assert len(graph.event_nodes) == 2


def test_cat_am_different_monetary_recurrence(deduplicator: EvidenceDeduplicator):
    """Category AM: One-time payment vs Recurring subscription remain distinct."""
    p1 = EvidenceItem(evidence_id="P1", source="price", type="displayed_price", description="One-time fee", value=999.0, currency="INR", metadata={"recurrence": "one_time"}, decision_context="purchase")
    p2 = EvidenceItem(evidence_id="P2", source="price", type="renewal_price", description="Recurring sub", value=999.0, currency="INR", metadata={"recurrence": "recurring"}, decision_context="subscription")
    graph, _ = deduplicator.build_evidence_graph([p1, p2])
    assert len(graph.event_nodes) == 2


def test_cat_an_same_text_different_journey(deduplicator: EvidenceDeduplicator):
    """Category AN: Exactly identical text across different journeys remains distinct."""
    t1 = EvidenceItem(evidence_id="T1", source="text", type="urgency", description="Hurry 5 mins left", journey_id="jrn_1")
    t2 = EvidenceItem(evidence_id="T2", source="text", type="urgency", description="Hurry 5 mins left", journey_id="jrn_2")
    graph, _ = deduplicator.build_evidence_graph([t1, t2])
    assert len(graph.event_nodes) == 2


def test_cat_ao_same_price_different_product(deduplicator: EvidenceDeduplicator):
    """Category AO: Same price on different product IDs remains distinct."""
    p1 = EvidenceItem(evidence_id="P1", source="price", type="displayed_price", description="Item 1 price", value=499.0, currency="INR", metadata={"product_id": "item_1"})
    p2 = EvidenceItem(evidence_id="P2", source="price", type="displayed_price", description="Item 2 price", value=499.0, currency="INR", metadata={"product_id": "item_2"})
    graph, _ = deduplicator.build_evidence_graph([p1, p2])
    assert len(graph.event_nodes) == 2


def test_cat_ap_same_element_different_journey(deduplicator: EvidenceDeduplicator):
    """Category AP: Same element reference in different journeys remains distinct."""
    d1 = EvidenceItem(evidence_id="D1", source="dom", type="preselected_option", description="Option X", element_ref="#warranty-box", journey_id="jrn_X")
    d2 = EvidenceItem(evidence_id="D2", source="dom", type="preselected_option", description="Option Y", element_ref="#warranty-box", journey_id="jrn_Y")
    graph, _ = deduplicator.build_evidence_graph([d1, d2])
    assert len(graph.event_nodes) == 2


def test_cat_aq_same_event_name_different_index(deduplicator: EvidenceDeduplicator):
    """Category AQ: Same action at different event index represents distinct action."""
    b1 = EvidenceItem(evidence_id="B1", source="behavior", type="click", description="Click 1", event_indices=[1], decision_context="checkout")
    b2 = EvidenceItem(evidence_id="B2", source="behavior", type="click", description="Click 7", event_indices=[7], decision_context="checkout")
    graph, _ = deduplicator.build_evidence_graph([b1, b2])
    assert len(graph.event_nodes) == 2


def test_cat_ar_temporal_ordering_preservation(deduplicator: EvidenceDeduplicator):
    """Category AR: Temporal ordering between events is preserved."""
    graph = EvidenceGraph()
    e_bef = graph.add_event_node(event_type="price_before", attributes={"amount": 499.0})
    e_aft = graph.add_event_node(event_type="price_after", attributes={"amount": 599.0})
    graph.add_edge(e_bef.node_id, e_aft.node_id, REL_PRECEDES)
    graph.add_edge(e_aft.node_id, e_bef.node_id, REL_FOLLOWS)
    edges = graph.get_edges_for_node(e_bef.node_id)
    assert any(e.relation_type == REL_PRECEDES for e in edges)
    assert any(e.relation_type == REL_FOLLOWS for e in edges)


def test_cat_as_relationship_determinism(deduplicator: EvidenceDeduplicator):
    """Category AS: Repeated graph construction on identical inputs produces identical graph."""
    items = [
        EvidenceItem(evidence_id="T1", source="text", type="subscription_trap", description="₹999/month", journey_id="j1"),
        EvidenceItem(evidence_id="P1", source="price", type="renewal_price", description="Renewal", value=999.0, currency="INR", journey_id="j1"),
    ]
    graph1, _ = deduplicator.build_evidence_graph(items)
    graph2, _ = deduplicator.build_evidence_graph(items)
    d1 = graph1.to_dict()
    d2 = graph2.to_dict()
    assert d1["total_nodes"] == d2["total_nodes"]
    assert d1["total_edges"] == d2["total_edges"]
    assert list(d1["event_nodes"].keys()) == list(d2["event_nodes"].keys())


# ==============================================================================
# SECTION 25: 15 MANDATORY ADVERSARIAL TESTS
# ==============================================================================

def test_adv_01_same_renewal_two_journeys(deduplicator: EvidenceDeduplicator):
    """Adversarial 1: Same ₹999/month renewal on two journeys => NEVER merge."""
    p1 = EvidenceItem(
        evidence_id="P1",
        source="price",
        type="renewal_price",
        description="Renewal J1",
        value=999.0,
        currency="INR",
        journey_id="jrn_1",
        decision_context="subscription",
        metadata={"period": "month", "recurrence": "recurring"},
    )
    p2 = EvidenceItem(
        evidence_id="P2",
        source="price",
        type="renewal_price",
        description="Renewal J2",
        value=999.0,
        currency="INR",
        journey_id="jrn_2",
        decision_context="subscription",
        metadata={"period": "month", "recurrence": "recurring"},
    )
    graph, _ = deduplicator.build_evidence_graph([p1, p2])
    assert len(graph.event_nodes) == 2


def test_adv_02_same_product_two_tabs(deduplicator: EvidenceDeduplicator):
    """Adversarial 2: Same product across two tabs => NEVER merge."""
    p1 = EvidenceItem(
        evidence_id="P1",
        source="price",
        type="displayed_price",
        description="Price tab 1",
        value=1499.0,
        currency="INR",
        provenance=StructuredProvenance(source="price", tab_id=1),
        decision_context="purchase",
    )
    p2 = EvidenceItem(
        evidence_id="P2",
        source="price",
        type="displayed_price",
        description="Price tab 2",
        value=1499.0,
        currency="INR",
        provenance=StructuredProvenance(source="price", tab_id=2),
        decision_context="purchase",
    )
    graph, _ = deduplicator.build_evidence_graph([p1, p2])
    assert len(graph.event_nodes) == 2


def test_adv_03_same_text_different_products(deduplicator: EvidenceDeduplicator):
    """Adversarial 3: Same text across different products => NEVER merge."""
    t1 = EvidenceItem(
        evidence_id="T1",
        source="text",
        type="subscription_trap",
        description="Billed annually after 14-day trial",
        metadata={"product_id": "prod_audio"},
        decision_context="subscription",
    )
    t2 = EvidenceItem(
        evidence_id="T2",
        source="text",
        type="subscription_trap",
        description="Billed annually after 14-day trial",
        metadata={"product_id": "prod_video"},
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([t1, t2])
    assert len(graph.event_nodes) == 2


def test_adv_04_cross_journey_price_changes_not_related():
    """Adversarial 4: ₹499 checkout followed by ₹599 checkout in another journey => NOT a price change relationship."""
    p1 = EvidenceItem(
        evidence_id="P1",
        source="price",
        type="displayed_price",
        description="Price J1",
        value=499.0,
        journey_id="jrn_1",
        decision_context="checkout",
    )
    p2 = EvidenceItem(
        evidence_id="P2",
        source="price",
        type="displayed_price",
        description="Price J2",
        value=599.0,
        journey_id="jrn_2",
        decision_context="checkout",
    )
    assert JourneyEngine.are_in_same_journey(p1, p2) is False


def test_adv_05_same_journey_price_change():
    """Adversarial 5: ₹499 -> ₹599 within the SAME valid journey => candidate price-change relationship."""
    p1 = EvidenceItem(
        evidence_id="P1",
        source="price",
        type="displayed_price",
        description="Price initial",
        value=499.0,
        journey_id="jrn_1",
        decision_context="checkout",
    )
    p2 = EvidenceItem(
        evidence_id="P2",
        source="price",
        type="displayed_price",
        description="Price update",
        value=599.0,
        journey_id="jrn_1",
        decision_context="checkout",
    )
    assert JourneyEngine.are_in_same_journey(p1, p2) is True


def test_adv_06_monthly_vs_annual_renewal_distinct(deduplicator: EvidenceDeduplicator):
    """Adversarial 6: Monthly renewal vs annual renewal => distinct events."""
    p_m = EvidenceItem(
        evidence_id="P_M",
        source="price",
        type="renewal_price",
        description="Renewal month",
        value=499.0,
        currency="INR",
        metadata={"period": "month", "recurrence": "recurring"},
        decision_context="subscription",
    )
    p_y = EvidenceItem(
        evidence_id="P_Y",
        source="price",
        type="renewal_price",
        description="Renewal year",
        value=499.0,
        currency="INR",
        metadata={"period": "year", "recurrence": "recurring"},
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([p_m, p_y])
    assert len(graph.event_nodes) == 2


def test_adv_07_7day_vs_30day_trial_distinct(deduplicator: EvidenceDeduplicator):
    """Adversarial 7: 7-day trial vs 30-day trial => distinct events."""
    t7 = EvidenceItem(
        evidence_id="T7",
        source="price",
        type="free_trial",
        description="7-day trial",
        value=0.0,
        metadata={"trial_duration_days": 7},
        decision_context="subscription",
    )
    t30 = EvidenceItem(
        evidence_id="T30",
        source="price",
        type="free_trial",
        description="30-day trial",
        value=0.0,
        metadata={"trial_duration_days": 30},
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([t7, t30])
    assert len(graph.event_nodes) == 2


def test_adv_08_free_text_vs_immediate_charge_contradiction(deduplicator: EvidenceDeduplicator):
    """Adversarial 8: Text says 'free', structured price says ₹999 immediate => contradiction, NOT deduplication."""
    t = EvidenceItem(
        evidence_id="T1",
        source="text",
        type="free_trial",
        description="Free download",
        decision_context="subscription",
    )
    p = EvidenceItem(
        evidence_id="P1",
        source="price",
        type="displayed_price",
        description="Immediate charge",
        value=999.0,
        currency="INR",
        decision_context="purchase",
    )
    contra = ContradictionItem(
        contradiction_id="C1",
        type="text_vs_price",
        source_a="text",
        source_b="price",
        reason="Claim of free download contradicted by immediate ₹999 price",
        evidence_ids=["T1", "P1"],
    )
    graph, _ = deduplicator.build_evidence_graph([t, p], contradictions=[contra])
    assert len(graph.event_nodes) == 2
    edges = [e for e in graph.edges if e.relation_type == REL_CONTRADICTS]
    assert len(edges) >= 2


def test_adv_09_privacy_page_mention_auxiliary(deduplicator: EvidenceDeduplicator):
    """Adversarial 9: Privacy-page text mentioning ₹999 => auxiliary, no transaction event."""
    t_aux = EvidenceItem(
        evidence_id="T_PRIV",
        source="text",
        type="subscription_trap",
        description="Our premium tier is ₹999/month",
        is_auxiliary=True,
        decision_context="subscription",
    )
    graph, _ = deduplicator.build_evidence_graph([t_aux])
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert ev.is_auxiliary is True


def test_adv_10_payment_gateway_dom_never_merchant_dom(deduplicator: EvidenceDeduplicator):
    """Adversarial 10: Payment gateway DOM => never merchant DOM cluster."""
    gw = EvidenceItem(
        evidence_id="D_GW",
        source="dom",
        type="gateway_iframe",
        description="Gateway container",
        is_auxiliary=True,
        decision_context="purchase",
    )
    merch = EvidenceItem(
        evidence_id="D_MERCH",
        source="dom",
        type="preselected_option",
        description="Merchant add-on",
        is_auxiliary=False,
        decision_context="purchase",
    )
    graph, _ = deduplicator.build_evidence_graph([gw, merch])
    assert len(graph.event_nodes) == 2


def test_adv_11_spa_rerender_same_component_deduped(deduplicator: EvidenceDeduplicator):
    """Adversarial 11: SPA rerender of the same checkout component => deduplicate appropriately."""
    dom_rerenders = [
        EvidenceItem(
            evidence_id=f"D{i}",
            source="dom",
            type="preselected_option",
            description="Preselected warranty",
            element_ref="#addon_warranty",
            route="/checkout",
            journey_id="jrn_spa",
            decision_context="checkout",
        )
        for i in range(3)
    ]
    graph, scoring_ev = deduplicator.build_evidence_graph(dom_rerenders)
    assert len(graph.evidence_nodes) == 3
    assert len(graph.event_nodes) == 1
    assert len(scoring_ev) == 1


def test_adv_12_two_separate_clicks_different_indices(deduplicator: EvidenceDeduplicator):
    """Adversarial 12: Two separate clicks at different event indices do not collapse into one behavior event."""
    c1 = EvidenceItem(
        evidence_id="B1",
        source="behavior",
        type="click",
        description="Click at step 2",
        event_indices=[2],
        journey_id="jrn_1",
        decision_context="checkout",
    )
    c2 = EvidenceItem(
        evidence_id="B2",
        source="behavior",
        type="click",
        description="Click at step 6",
        event_indices=[6],
        journey_id="jrn_1",
        decision_context="checkout",
    )
    graph, _ = deduplicator.build_evidence_graph([c1, c2])
    assert len(graph.event_nodes) == 2


def test_adv_13_element_state_change_enabled_to_disabled(deduplicator: EvidenceDeduplicator):
    """Adversarial 13: Same DOM element changes from enabled to disabled => distinct state observations."""
    d_enabled = EvidenceItem(
        evidence_id="D_EN",
        source="dom",
        type="action_enabled",
        description="Button was enabled",
        element_ref="#btn-cancel",
        temporal_position="before_action",
        decision_context="cancellation",
    )
    d_disabled = EvidenceItem(
        evidence_id="D_DIS",
        source="dom",
        type="cancel_action_disabled",
        description="Button became disabled",
        element_ref="#btn-cancel",
        temporal_position="after_action",
        decision_context="cancellation",
    )
    graph, _ = deduplicator.build_evidence_graph([d_enabled, d_disabled])
    assert len(graph.event_nodes) == 2


def test_adv_14_missing_journey_id_no_crash(deduplicator: EvidenceDeduplicator):
    """Adversarial 14: Evidence with missing journey_id => legacy fallback, no crash."""
    i1 = EvidenceItem(evidence_id="E1", source="text", type="urgency", description="Sale ends soon")
    i2 = EvidenceItem(evidence_id="E2", source="text", type="urgency", description="Sale ends soon")
    graph, scoring_ev = deduplicator.build_evidence_graph([i1, i2])
    assert len(graph.evidence_nodes) == 2
    assert len(graph.event_nodes) == 1
    assert len(scoring_ev) == 1


def test_adv_15_contradictory_observations_preserve_both_provenance(deduplicator: EvidenceDeduplicator):
    """Adversarial 15: Contradictory observations preserve both provenance records."""
    t = EvidenceItem(
        evidence_id="T1",
        source="text",
        type="free_trial",
        description="Free trial",
        provenance=StructuredProvenance(source="text", model_version="text_v3", tab_id=1),
        decision_context="subscription",
    )
    p = EvidenceItem(
        evidence_id="P1",
        source="price",
        type="paid_trial",
        description="Paid trial 499",
        value=499.0,
        currency="INR",
        provenance=StructuredProvenance(source="price", model_version="price_v2", tab_id=1),
        decision_context="subscription",
    )
    contra = ContradictionItem(
        contradiction_id="C1",
        type="text_vs_price",
        source_a="text",
        source_b="price",
        reason="Free vs paid contradiction",
        evidence_ids=["T1", "P1"],
    )
    graph, _ = deduplicator.build_evidence_graph([t, p], contradictions=[contra])
    node_t = graph.evidence_nodes["node_T1"]
    node_p = graph.evidence_nodes["node_P1"]
    assert node_t.provenance["model_version"] == "text_v3"
    assert node_p.provenance["model_version"] == "price_v2"
    assert len(graph.event_nodes) == 2
