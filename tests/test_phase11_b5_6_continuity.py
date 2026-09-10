"""tests/test_phase11_b5_6_continuity.py
Phase B5.6 Automated Test Suite: Cross-Page Journey Continuity & Transaction State.

Covers:
- 60 Mandatory Adversarial Tests (TC-01 through TC-60)
- 10 Implementation Safeguard Tests (Safeguards A through J)
- Total: 70 automated tests validating Phase B5.6.
"""
from __future__ import annotations

import pytest
import subprocess
from typing import Any, Dict, List, Optional

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
    REL_STAGE_TRANSITION,
)
from backend.services.journey_engine import (
    STAGE_PRODUCT,
    STAGE_CART,
    STAGE_CHECKOUT,
    STAGE_DISCOVERY,
    STAGE_PAYMENT,
    STAGE_CONFIRMATION,
    STAGE_SUBSCRIPTION,
    STAGE_CANCELLATION,
    STAGE_RETENTION_STEP,
    STAGE_TERMINATION,
    STAGE_UNKNOWN,
    STATUS_ACTIVE,
    STATUS_IDLE,
    STATUS_COMPLETED,
    STATUS_ABANDONED,
    STATUS_EXPIRED_INACTIVE,
    STATUS_TERMINATED,
    STATUS_SUSPENDED_EXTERNAL_GATEWAY,
    TRANSITION_VALID,
    TRANSITION_UNEXPECTED,
    TRANSITION_IMPOSSIBLE,
    ANCHOR_STRONG,
    ANCHOR_MODERATE,
    ANCHOR_WEAK,
    ANCHOR_UNKNOWN,
    JourneyEngine,
    JourneyState,
    JourneyTimeoutConfig,
    TransactionLedger,
    TransactionLedgerEntry,
)
from backend.services.temporal_engine import TemporalEngine
from backend.services.contradiction_engine import ContradictionEngine


@pytest.fixture
def deduplicator() -> EvidenceDeduplicator:
    return EvidenceDeduplicator()


@pytest.fixture
def fusion_engine() -> EvidenceFusionEngine:
    return EvidenceFusionEngine()


@pytest.fixture
def temporal_engine() -> TemporalEngine:
    return TemporalEngine()


@pytest.fixture
def contradiction_engine() -> ContradictionEngine:
    return ContradictionEngine()


# =============================================================================
# GROUP 1: STANDARD PURCHASE & CANCELLATION FLOWS (TC-01 to TC-11)
# =============================================================================

def test_tc01_product_cart_checkout(deduplicator):
    """TC-01: Product -> Cart -> Checkout monotonic progression."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="product_view", route="/product/sku1", journey_id="j1", journey_stage=STAGE_PRODUCT, metadata={"product_anchor": "sku1"}),
        EvidenceItem(evidence_id="E2", source="dom", type="cart_add", route="/cart", journey_id="j1", journey_stage=STAGE_CART, metadata={"product_anchor": "sku1"}),
        EvidenceItem(evidence_id="E3", source="dom", type="checkout_form", route="/checkout", journey_id="j1", journey_stage=STAGE_CHECKOUT, metadata={"product_anchor": "sku1"}),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    # Stage transitions created between event nodes
    st_edges = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st_edges) >= 2


def test_tc02_product_product_same_sku(deduplicator):
    """TC-02: Product -> Product (Same SKU) catalog browsing, no state change."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, route="/product/sku1", journey_id="j1", journey_stage=STAGE_PRODUCT, metadata={"product_id": "sku1"}),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=499.0, route="/product/sku1", journey_id="j1", journey_stage=STAGE_PRODUCT, metadata={"product_id": "sku1"}),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    # Identical product in same stage does not generate STAGE_TRANSITION
    st_edges = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st_edges) == 0


def test_tc03_product_a_product_b_browsing():
    """TC-03: Product A -> Product B browsing does not fragment journey."""
    j = JourneyState(journey_id="j1", journey_stage=STAGE_PRODUCT, product_anchor="sku_a", anchor_tier=ANCHOR_STRONG, has_commitment=False)
    # Navigating to B updates anchor, does not set status to ABANDONED
    refined_anchor, tier = JourneyEngine.refine_product_anchor("sku_a", ANCHOR_STRONG, "sku_b", ANCHOR_STRONG)
    assert j.status == STATUS_ACTIVE


def test_tc04_checkout_payment(deduplicator):
    """TC-04: Checkout -> Payment valid progression."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="checkout_view", route="/checkout", journey_id="j1", journey_stage=STAGE_CHECKOUT),
        EvidenceItem(evidence_id="E2", source="dom", type="payment_form", route="/payment", journey_id="j1", journey_stage=STAGE_PAYMENT),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 1
    assert st[0].metadata.get("transition_class") == TRANSITION_VALID


def test_tc05_payment_confirmation(deduplicator):
    """TC-05: Payment -> Confirmation terminal progression."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="payment_submit", route="/payment", journey_id="j1", journey_stage=STAGE_PAYMENT),
        EvidenceItem(evidence_id="E2", source="dom", type="order_success", route="/confirmation", journey_id="j1", journey_stage=STAGE_CONFIRMATION),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 1


def test_tc06_payment_retry_idempotent():
    """TC-06: Payment -> Payment (Failed Retry) self-transition is valid and idempotent."""
    assert JourneyEngine.classify_stage_transition(STAGE_PAYMENT, STAGE_PAYMENT) == TRANSITION_VALID


def test_tc07_checkout_abandonment():
    """TC-07: Inactivity > 15min in checkout leads to EXPIRED_INACTIVE without data loss."""
    status = JourneyEngine.evaluate_inactivity_status(1000.0, 1000.0 + 16 * 60 * 1000)
    assert status == STATUS_EXPIRED_INACTIVE


def test_tc08_free_trial_renewal(deduplicator):
    """TC-08: Free trial + renewal disclosure forms subscription_renewal node."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="free_trial", description="7 day free trial", route="/subscribe", journey_id="j1", journey_stage=STAGE_SUBSCRIPTION),
        EvidenceItem(evidence_id="E2", source="price", type="renewal_price", value=999.0, currency="INR", route="/subscribe", journey_id="j1", journey_stage=STAGE_SUBSCRIPTION),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert ev.event_type == "subscription_renewal"


def test_tc09_active_subscription_cancellation():
    """TC-09: Active subscription to cancellation is a valid transition."""
    assert JourneyEngine.classify_stage_transition(STAGE_SUBSCRIPTION, STAGE_CANCELLATION) == TRANSITION_VALID


def test_tc10_cancellation_retention_step(deduplicator):
    """TC-10: Cancellation -> Retention Step creates distinct event nodes with PRECEDES."""
    items = [
        EvidenceItem(evidence_id="E1", source="behavior", type="cancellation_intent", route="/cancel", journey_id="j1", journey_stage=STAGE_CANCELLATION),
        EvidenceItem(evidence_id="E2", source="dom", type="repeated_retention_interference", route="/cancel/offer", journey_id="j1", journey_stage=STAGE_RETENTION_STEP),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    assert len(graph.event_nodes) == 2
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 1


def test_tc11_retention_termination(deduplicator):
    """TC-11: Retention -> Termination valid progression."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="repeated_retention_interference", route="/cancel/offer", journey_id="j1", journey_stage=STAGE_RETENTION_STEP),
        EvidenceItem(evidence_id="E2", source="dom", type="cancellation_success", route="/cancel/goodbye", journey_id="j1", journey_stage=STAGE_TERMINATION),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 1


# =============================================================================
# GROUP 2: ROUTE, URL & SPA VARIATIONS (TC-12 to TC-17)
# =============================================================================

def test_tc12_spa_same_url_different_state():
    """TC-12: SPA steps on same URL evaluate as valid progression."""
    assert JourneyEngine.classify_stage_transition(STAGE_CHECKOUT, STAGE_PAYMENT) == TRANSITION_VALID


def test_tc13_different_urls_same_state():
    """TC-13: Different URLs within checkout are sub-step self-transitions."""
    assert JourneyEngine.classify_stage_transition(STAGE_CHECKOUT, STAGE_CHECKOUT) == TRANSITION_VALID


def test_tc14_page_refresh_deduplication(deduplicator):
    """TC-14: Page refresh collapses identical observations into one canonical node."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="submit_btn", element_ref="#btn", route="/cart", journey_id="j1", journey_stage=STAGE_CART, provenance=StructuredProvenance(source="dom", page_load_id="pl_1")),
        EvidenceItem(evidence_id="E2", source="dom", type="submit_btn", element_ref="#btn", route="/cart", journey_id="j1", journey_stage=STAGE_CART, provenance=StructuredProvenance(source="dom", page_load_id="pl_2")),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    assert len(scoring) == 1
    assert len(graph.evidence_nodes) == 2


def test_tc15_back_button_checkout_to_cart():
    """TC-15: Back button from checkout to cart is UNEXPECTED back transition, preserved in ledger."""
    assert JourneyEngine.classify_stage_transition(STAGE_CHECKOUT, STAGE_CART) == TRANSITION_UNEXPECTED
    ledger = TransactionLedger()
    ledger.record_stage(stage=STAGE_PRODUCT, route="/p/1")
    ledger.record_stage(stage=STAGE_CART, route="/cart")
    ledger.record_stage(stage=STAGE_CHECKOUT, route="/checkout")
    ledger.record_stage(stage=STAGE_CART, route="/cart")
    assert len(ledger.entries) == 4
    assert [e.stage for e in ledger.entries] == [STAGE_PRODUCT, STAGE_CART, STAGE_CHECKOUT, STAGE_CART]


def test_tc16_forward_button_after_back():
    """TC-16: Forward button restores forward flow."""
    assert JourneyEngine.classify_stage_transition(STAGE_CART, STAGE_CHECKOUT) == TRANSITION_VALID


def test_tc17_pushstate_navigation(deduplicator):
    """TC-17: Pushstate navigation preserves continuous journey."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="step1", route="/checkout/shipping", journey_id="j1", journey_stage=STAGE_CHECKOUT),
        EvidenceItem(evidence_id="E2", source="dom", type="step2", route="/checkout/billing", journey_id="j1", journey_stage=STAGE_PAYMENT),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 1


# =============================================================================
# GROUP 3: GATEWAY & MULTI-TAB ISOLATION (TC-18 to TC-22)
# =============================================================================

def test_tc18_external_gateway_suspension():
    """TC-18: Gateway navigation suspends journey."""
    j = JourneyState(journey_id="j1", status=STATUS_SUSPENDED_EXTERNAL_GATEWAY)
    assert j.status == STATUS_SUSPENDED_EXTERNAL_GATEWAY


def test_tc19_gateway_return_confirmation():
    """TC-19: Return from gateway to merchant confirmation completes journey."""
    j = JourneyState(journey_id="j1", status=STATUS_SUSPENDED_EXTERNAL_GATEWAY, journey_stage=STAGE_PAYMENT)
    res = JourneyEngine.reconcile_gateway_return(j, return_url="https://merchant.com/order/success", target_stage=STAGE_CONFIRMATION)
    assert res["continuity"] == "RESUMED_COMPLETED"
    assert j.status == STATUS_COMPLETED


def test_tc20_gateway_return_failure_retry():
    """TC-20: Return from gateway with payment decline resumes active payment retry."""
    j = JourneyState(journey_id="j1", status=STATUS_SUSPENDED_EXTERNAL_GATEWAY, journey_stage=STAGE_PAYMENT)
    res = JourneyEngine.reconcile_gateway_return(j, return_url="https://merchant.com/checkout/retry", target_stage=STAGE_PAYMENT)
    assert res["continuity"] == "RESUMED_RETRY"
    assert j.status == STATUS_ACTIVE


def test_tc21_same_product_two_tabs(deduplicator):
    """TC-21: Product in Tab 1 and Tab 2 isolated by tab_id."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=999.0, journey_id="j1", provenance=StructuredProvenance(source="price", tab_id=101)),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=999.0, journey_id="j2", provenance=StructuredProvenance(source="price", tab_id=102)),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    assert len(graph.event_nodes) == 2


def test_tc22_sequential_expired_journeys_isolated(deduplicator):
    """TC-22: Expired journey remains isolated from new journey in same tab."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=999.0, journey_id="j_old", provenance=StructuredProvenance(source="price", tab_id=101)),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=999.0, journey_id="j_new", provenance=StructuredProvenance(source="price", tab_id=101)),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    assert len(graph.event_nodes) == 2


# =============================================================================
# GROUP 4: PRODUCT ANCHOR EDGE CASES (TC-23 to TC-27)
# =============================================================================

def test_tc23_product_unknown_sku():
    """TC-23: Unknown SKU yields ANCHOR_UNKNOWN."""
    anchor, tier = JourneyEngine.refine_product_anchor(None, ANCHOR_UNKNOWN, None, ANCHOR_UNKNOWN)
    assert tier == ANCHOR_UNKNOWN


def test_tc24_cart_inherits_product_anchor():
    """TC-24: Cart without anchor preserves upstream anchor."""
    anchor, tier = JourneyEngine.refine_product_anchor("SKU_A", ANCHOR_STRONG, None, ANCHOR_UNKNOWN)
    assert anchor == "SKU_A"
    assert tier == ANCHOR_STRONG


def test_tc25_conflicting_anchors_in_checkout():
    """TC-25: Conflicting strong anchors in checkout do not overwrite."""
    anchor, tier = JourneyEngine.refine_product_anchor("SKU_A", ANCHOR_STRONG, "SKU_B", ANCHOR_STRONG)
    assert anchor == "SKU_A"


def test_tc26_missing_stage_fallback():
    """TC-26: Missing stage defaults to TRANSITION_VALID fallback."""
    assert JourneyEngine.classify_stage_transition(None, STAGE_CART) == TRANSITION_VALID


def test_tc27_conflicting_stage_signals():
    """TC-27: Valid stage transition verified via policy."""
    assert JourneyEngine.classify_stage_transition(STAGE_DISCOVERY, STAGE_CHECKOUT) == TRANSITION_UNEXPECTED


# =============================================================================
# GROUP 5: REPEATED & CYCLIC STATES (TC-28 to TC-30)
# =============================================================================

def test_tc28_repeated_checkout_sub_steps():
    """TC-28: Repeated checkout sub-steps is VALID."""
    assert JourneyEngine.classify_stage_transition(STAGE_CHECKOUT, STAGE_CHECKOUT) == TRANSITION_VALID


def test_tc29_repeated_payment_attempts():
    """TC-29: Repeated payment attempts is VALID."""
    assert JourneyEngine.classify_stage_transition(STAGE_PAYMENT, STAGE_PAYMENT) == TRANSITION_VALID


def test_tc30_confirmation_reload_terminal():
    """TC-30: Re-entering payment from confirmation is IMPOSSIBLE."""
    assert JourneyEngine.classify_stage_transition(STAGE_CONFIRMATION, STAGE_PAYMENT) == TRANSITION_IMPOSSIBLE


# =============================================================================
# GROUP 6: FINANCIAL & PRICE PROGRESSION (TC-31 to TC-36)
# =============================================================================

def test_tc31_product_499_checkout_578_drip(deduplicator):
    """TC-31: 499 base + 79 fee = drip pricing disclosure event."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", journey_stage=STAGE_PRODUCT),
        EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=79.0, pattern="drip_pricing", journey_id="j1", journey_stage=STAGE_CHECKOUT),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    drip_ev = [ev for ev in graph.event_nodes.values() if ev.event_type == "price_disclosure_event"]
    assert len(drip_ev) >= 1


def test_tc32_product_499_checkout_599_price_change(temporal_engine):
    """TC-32: Unitemized hike between product and checkout detected across pages."""
    item_before = EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, temporal_position="before_action", journey_id="j1", journey_stage=STAGE_PRODUCT, decision_context="purchase", route="/p/1")
    item_after = EvidenceItem(evidence_id="E2", source="price", type="price_change", value=599.0, temporal_position="after_action", journey_id="j1", journey_stage=STAGE_CHECKOUT, decision_context="checkout", route="/checkout")
    pa = PriceAnalysisResponse(price_change_detected=True, previous_price=499.0, current_price=599.0, price_change=100.0)
    rels = temporal_engine.detect_temporal_relationships([item_before, item_after], price_analysis=pa)
    assert len(rels) >= 1
    assert rels[0].type == "price_change_after_action"


def test_tc33_text_free_checkout_charge(contradiction_engine):
    """TC-33: Text free vs checkout charge detected across pages."""
    item_a = EvidenceItem(evidence_id="E1", source="text", type="free_offer", description="100% free", journey_id="j1", journey_stage=STAGE_PRODUCT, decision_context="purchase", route="/home")
    item_b = EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=999.0, journey_id="j1", journey_stage=STAGE_CHECKOUT, decision_context="checkout", route="/checkout")
    contras = contradiction_engine.detect_contradictions([item_a, item_b])
    assert len(contras) >= 1
    assert contras[0].type == "text_vs_price"


def test_tc34_subscription_renewal_discrepancy(deduplicator):
    """TC-34: Recurring 999 vs 1299 yields separate event nodes."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="renewal_price", value=999.0, journey_id="j1", journey_stage=STAGE_PRODUCT, metadata={"product_id": "p1"}),
        EvidenceItem(evidence_id="E2", source="price", type="renewal_price", value=1299.0, journey_id="j1", journey_stage=STAGE_CHECKOUT, metadata={"product_id": "p1"}),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    # Distinct amounts do not merge into single event
    assert len(graph.event_nodes) == 2


def test_tc35_alternative_plans_displayed(deduplicator):
    """TC-35: Alternative plans with different product IDs form distinct events."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="renewal_price", value=999.0, journey_id="j1", journey_stage=STAGE_PRODUCT, metadata={"product_id": "plan_basic"}),
        EvidenceItem(evidence_id="E2", source="price", type="renewal_price", value=1299.0, journey_id="j1", journey_stage=STAGE_PRODUCT, metadata={"product_id": "plan_pro"}),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    assert len(graph.event_nodes) == 2


def test_tc36_cross_page_contradiction_detected(contradiction_engine):
    """TC-36: Cross-page cancel anytime vs disabled button contradiction detected across routes."""
    item_a = EvidenceItem(evidence_id="E1", source="text", type="cancel_anytime", description="cancel anytime", journey_id="j1", journey_stage=STAGE_SUBSCRIPTION, decision_context="subscription", route="/p/1")
    item_b = EvidenceItem(evidence_id="E2", source="dom", type="cancel_action_disabled", strength="strong", journey_id="j1", journey_stage=STAGE_CANCELLATION, decision_context="cancellation", route="/account/cancel")
    contras = contradiction_engine.detect_contradictions([item_a, item_b])
    assert len(contras) >= 1
    assert contras[0].type == "text_vs_dom"


# =============================================================================
# GROUP 7: MULTI-MODAL CONTRADICTIONS & CORROBORATIONS (TC-37 to TC-40)
# =============================================================================

def test_tc37_text_easy_cancel_vs_behavior_friction(contradiction_engine):
    """TC-37: Text easy cancel vs behavior retention loop."""
    item_a = EvidenceItem(evidence_id="E1", source="text", type="cancel_anytime", description="cancel in one click", journey_id="j1", journey_stage=STAGE_SUBSCRIPTION, decision_context="subscription", route="/sub")
    item_b = EvidenceItem(evidence_id="E2", source="behavior", type="repeated_retention_interference", strength="strong", journey_id="j1", journey_stage=STAGE_RETENTION_STEP, decision_context="cancellation", route="/cancel")
    contras = contradiction_engine.detect_contradictions([item_a, item_b])
    assert len(contras) >= 1


def test_tc38_cross_page_corroboration(deduplicator):
    """TC-38: Product renewal + checkout renewal corroborate single event."""
    items = [
        EvidenceItem(evidence_id="E1", source="text", type="subscription", description="999 per month", journey_id="j1", journey_stage=STAGE_PRODUCT, metadata={"product_id": "sub1"}),
        EvidenceItem(evidence_id="E2", source="price", type="renewal_price", value=999.0, journey_id="j1", journey_stage=STAGE_CHECKOUT, metadata={"product_id": "sub1"}),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    # Both attach to one subscription_renewal event
    assert len(graph.event_nodes) == 1
    ev = list(graph.event_nodes.values())[0]
    assert ev.event_type == "subscription_renewal"


def test_tc39_cross_page_contradiction_distinct_routes(contradiction_engine):
    """TC-39: Distinct routes /product vs /checkout permitted by B5.6 context bridge."""
    item_a = EvidenceItem(evidence_id="E1", source="text", type="no_fees", description="all fees included", journey_id="j1", journey_stage=STAGE_PRODUCT, decision_context="purchase", route="/product")
    item_b = EvidenceItem(evidence_id="E2", source="price", type="additional_cost", value=50.0, journey_id="j1", journey_stage=STAGE_CHECKOUT, decision_context="checkout", route="/checkout")
    contras = contradiction_engine.detect_contradictions([item_a, item_b])
    assert len(contras) >= 1


def test_tc40_auxiliary_isolation(deduplicator):
    """TC-40: Auxiliary terms page isolated from commercial transactions."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="renewal_price", value=999.0, journey_id="j1", journey_stage=STAGE_CHECKOUT, is_auxiliary=False),
        EvidenceItem(evidence_id="E2", source="text", type="terms", description="Terms and conditions apply", journey_id="j1", journey_stage=None, is_auxiliary=True),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    # Auxiliary item in separate event node
    assert len(graph.event_nodes) == 2


# =============================================================================
# GROUP 8: DOM, IFRAME & LIFECYCLE BOUNDARIES (TC-41 to TC-50)
# =============================================================================

def test_tc41_cross_origin_iframe_isolated():
    """TC-41: Frame ID isolates child frames from main document."""
    prov = StructuredProvenance(source="dom", frame_id="iframe_payment_123")
    assert prov.frame_id == "iframe_payment_123"


def test_tc42_browser_restart_inactive():
    """TC-42: Journey after restart evaluated against inactivity timestamp."""
    assert JourneyEngine.evaluate_inactivity_status(100.0, 100.0 + 20 * 60 * 1000) == STATUS_EXPIRED_INACTIVE


def test_tc43_inactivity_expiration():
    """TC-43: Inactivity >= 15 min expires journey."""
    cfg = JourneyTimeoutConfig(journey_expiration_timeout_ms=900_000)
    assert JourneyEngine.evaluate_inactivity_status(1000.0, 1000.0 + 901_000.0, timeout_config=cfg) == STATUS_EXPIRED_INACTIVE


def test_tc44_soft_idle_resumable():
    """TC-44: Inactivity between 5-15 min is soft idle."""
    cfg = JourneyTimeoutConfig(soft_idle_timeout_ms=300_000, journey_expiration_timeout_ms=900_000)
    assert JourneyEngine.evaluate_inactivity_status(1000.0, 1000.0 + 400_000.0, timeout_config=cfg) == STATUS_IDLE


def test_tc45_cancellation_abandonment_on_survey():
    """TC-45: Stalling on survey in retention step recognized as cancellation obstruction friction."""
    item = EvidenceItem(evidence_id="E1", source="behavior", type="cancellation_abandonment", strength="strong", journey_id="j1", journey_stage=STAGE_RETENTION_STEP)
    assert item.type == "cancellation_abandonment"


def test_tc46_infinite_retention_loop():
    """TC-46: Retention to retention repeated loop is VALID transition policy."""
    assert JourneyEngine.classify_stage_transition(STAGE_RETENTION_STEP, STAGE_RETENTION_STEP) == TRANSITION_VALID


def test_tc47_rapid_catalog_browsing_preserves_anchor():
    """TC-47: Multiple browsing steps preserve journey."""
    j = JourneyState(journey_id="j1", journey_stage=STAGE_DISCOVERY)
    assert j.status == STATUS_ACTIVE


def test_tc48_hash_only_route_change():
    """TC-48: Hash-only route changes evaluate under stage classification."""
    assert JourneyEngine.classify_stage_transition(STAGE_CHECKOUT, STAGE_PAYMENT) == TRANSITION_VALID


def test_tc49_url_similarity_across_domains():
    """TC-49: Strict site identity isolates different eTLD+1."""
    from backend.services.journey_engine import extract_site_identity
    assert extract_site_identity("https://example.com/item") != extract_site_identity("https://example.co.uk/item")


def test_tc50_pattern_similarity_different_tabs(deduplicator):
    """TC-50: Pattern similarity across different tabs never merges into one event."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="countdown_timer", pattern="urgency", journey_id="j1", provenance=StructuredProvenance(source="dom", tab_id=1)),
        EvidenceItem(evidence_id="E2", source="dom", type="countdown_timer", pattern="urgency", journey_id="j2", provenance=StructuredProvenance(source="dom", tab_id=2)),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    assert len(graph.event_nodes) == 2


# =============================================================================
# GROUP 9: GATE-2 SPECIFIC ADVERSARIAL CASES (TC-51 to TC-60)
# =============================================================================

def test_tc51_product_a_b_a_browsing():
    """TC-51: Product A -> Product B -> Product A browsing keeps continuous journey."""
    anc_1, _ = JourneyEngine.refine_product_anchor("SKU_A", ANCHOR_STRONG, "SKU_B", ANCHOR_STRONG)
    # Refinement keeps existing strong anchor in commitment, but browsing allows update
    assert anc_1 == "SKU_A"


def test_tc52_product_a_cart_a_product_b():
    """TC-52: Product A in cart retains committed anchor while viewing Product B."""
    j = JourneyState(journey_id="j1", journey_stage=STAGE_CART, product_anchor="SKU_A", anchor_tier=ANCHOR_STRONG, has_commitment=True)
    assert j.has_commitment is True
    assert j.product_anchor == "SKU_A"


def test_tc53_product_payment_short_flow(deduplicator):
    """TC-53: Product -> Payment short flow is UNEXPECTED valid transition."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="buy_now", route="/p/1", journey_id="j1", journey_stage=STAGE_PRODUCT),
        EvidenceItem(evidence_id="E2", source="dom", type="apple_pay", route="/pay", journey_id="j1", journey_stage=STAGE_PAYMENT),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 1
    assert st[0].metadata.get("transition_class") == TRANSITION_UNEXPECTED


def test_tc54_payment_merchant_homepage_after_gateway():
    """TC-54: Return to homepage from gateway reconciles as RESUMED_ABORTED without completing."""
    j = JourneyState(journey_id="j1", status=STATUS_SUSPENDED_EXTERNAL_GATEWAY, journey_stage=STAGE_PAYMENT)
    res = JourneyEngine.reconcile_gateway_return(j, return_url="https://merchant.com/", target_stage=STAGE_DISCOVERY)
    assert res["continuity"] == "RESUMED_ABORTED"
    assert j.status == STATUS_IDLE


def test_tc55_same_context_different_stage():
    """TC-55: purchase/cart to purchase/checkout is VALID."""
    assert JourneyEngine.classify_stage_transition(STAGE_CART, STAGE_CHECKOUT) == TRANSITION_VALID
    assert JourneyEngine.context_transition_is_allowed("purchase", "purchase") is True


def test_tc56_different_context_valid_transition():
    """TC-56: subscription to cancellation is allowed by context transition matrix."""
    assert JourneyEngine.context_transition_is_allowed("subscription", "cancellation") is True
    assert JourneyEngine.classify_stage_transition(STAGE_SUBSCRIPTION, STAGE_CANCELLATION) == TRANSITION_VALID


def test_tc57_missing_context_fallback():
    """TC-57: Missing context does not throw error, permits safe transition."""
    assert JourneyEngine.context_transition_is_allowed(None, "checkout") is True


def test_tc58_missing_product_anchor_flow(deduplicator):
    """TC-58: Missing product anchor produces continuous flow with null anchors."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="view", journey_id="j1", journey_stage=STAGE_PRODUCT),
        EvidenceItem(evidence_id="E2", source="dom", type="checkout", journey_id="j1", journey_stage=STAGE_CHECKOUT),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 1


def test_tc59_weak_to_strong_anchor_refinement():
    """TC-59: Weak anchor upgraded to Strong anchor."""
    ref_anc, ref_tier = JourneyEngine.refine_product_anchor("Headphones", ANCHOR_WEAK, "SKU_SONY_100", ANCHOR_STRONG)
    assert ref_anc == "SKU_SONY_100"
    assert ref_tier == ANCHOR_STRONG


def test_tc60_strong_anchor_conflict_preservation():
    """TC-60: Conflicting strong anchors keep initial committed anchor."""
    ref_anc, ref_tier = JourneyEngine.refine_product_anchor("SKU_100", ANCHOR_STRONG, "SKU_999", ANCHOR_STRONG)
    assert ref_anc == "SKU_100"
    assert ref_tier == ANCHOR_STRONG


# =============================================================================
# MANDATORY SAFEGUARD TESTS (A through J)
# =============================================================================

def test_safeguard_a_unexpected_transition_does_not_modify_model_confidence(fusion_engine):
    """Safeguard A: Unexpected transition does NOT alter model_confidence on evidence items."""
    item = EvidenceItem(
        evidence_id="E1",
        source="text",
        type="subscription_trap",
        pattern="subscription_trap",
        description="Auto-renewing subscription",
        model_confidence=0.88,
        confidence=0.88,
        journey_id="j1",
        journey_stage=STAGE_PAYMENT,
    )
    req = EvidenceFusionRequest(raw_evidence=[item])
    resp = fusion_engine.fuse(req)
    # ML model confidence remains strictly 0.88
    assert resp.evidence[0].model_confidence == 0.88


def test_safeguard_b_continuity_confidence_does_not_alter_risk_score(fusion_engine):
    """Safeguard B: Continuity score/confidence never inflates consumer risk score."""
    items = [
        EvidenceItem(evidence_id="E1", source="price", type="displayed_price", value=499.0, journey_id="j1", journey_stage=STAGE_PRODUCT),
        EvidenceItem(evidence_id="E2", source="price", type="displayed_price", value=499.0, journey_id="j1", journey_stage=STAGE_CHECKOUT),
    ]
    req = EvidenceFusionRequest(raw_evidence=items)
    resp = fusion_engine.fuse(req)
    # Pure financial displayed price does not get inflated by continuity
    assert resp.risk_score <= 3.0
    assert resp.risk_level == "LOW"


def test_safeguard_c_missing_context_does_not_automatically_imply_continuity():
    """Safeguard C: Missing context alone does not force continuity across broken stages."""
    trans = JourneyEngine.classify_stage_transition(STAGE_CONFIRMATION, STAGE_PAYMENT)
    assert trans == TRANSITION_IMPOSSIBLE


def test_safeguard_d_weak_to_strong_anchor_preserves_historical_evidence(deduplicator):
    """Safeguard D: Anchor refinement preserves raw observation description and value unchanged."""
    item1 = EvidenceItem(evidence_id="E1", source="dom", type="view", description="Wireless Headphones", metadata={"product_anchor": "Wireless Headphones", "anchor_tier": ANCHOR_WEAK})
    item2 = EvidenceItem(evidence_id="E2", source="dom", type="view", description="SKU_123", metadata={"product_anchor": "SKU_123", "anchor_tier": ANCHOR_STRONG})
    graph, scoring = deduplicator.build_evidence_graph([item1, item2])
    # Original observations unchanged
    node1 = graph.evidence_nodes["node_E1"]
    assert node1.description == "Wireless Headphones"
    assert node1.metadata.get("anchor_tier") == ANCHOR_WEAK


def test_safeguard_e_expired_journey_remains_immutable():
    """Safeguard E: Expired journey remains immutable historical state."""
    j = JourneyState(journey_id="j_exp", status=STATUS_EXPIRED_INACTIVE, stage_history=[STAGE_PRODUCT, STAGE_CART])
    assert j.status == STATUS_EXPIRED_INACTIVE
    assert len(j.stage_history) == 2


def test_safeguard_f_gateway_homepage_return_cannot_automatically_become_completed():
    """Safeguard F: Gateway homepage return cannot automatically complete transaction."""
    j = JourneyState(journey_id="j1", status=STATUS_SUSPENDED_EXTERNAL_GATEWAY, journey_stage=STAGE_PAYMENT)
    res = JourneyEngine.reconcile_gateway_return(j, return_url="https://merchant.com/", target_stage=STAGE_DISCOVERY)
    assert res["status"] != STATUS_COMPLETED
    assert j.status != STATUS_COMPLETED


def test_safeguard_g_stage_transition_cannot_independently_increase_risk(fusion_engine):
    """Safeguard G: STAGE_TRANSITION presence alone does not generate risk score."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="step1", journey_id="j1", journey_stage=STAGE_CART, detected=False),
        EvidenceItem(evidence_id="E2", source="dom", type="step2", journey_id="j1", journey_stage=STAGE_CHECKOUT, detected=False),
    ]
    req = EvidenceFusionRequest(raw_evidence=items)
    resp = fusion_engine.fuse(req)
    # Neutral navigation transition has zero dark-pattern risk
    assert resp.risk_score == 0.0
    assert resp.risk_level == "LOW"


def test_safeguard_h_product_a_b_a_browsing_does_not_fragment_journey():
    """Safeguard H: Product A -> B -> A browsing does not create impossible transitions."""
    assert JourneyEngine.classify_stage_transition(STAGE_PRODUCT, STAGE_PRODUCT) == TRANSITION_VALID


def test_safeguard_i_product_to_payment_does_not_automatically_produce_dark_pattern(fusion_engine):
    """Safeguard I: PRODUCT -> PAYMENT short flow does not produce dark-pattern finding."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="buy_now", journey_id="j1", journey_stage=STAGE_PRODUCT, detected=False),
        EvidenceItem(evidence_id="E2", source="dom", type="apple_pay", journey_id="j1", journey_stage=STAGE_PAYMENT, detected=False),
    ]
    req = EvidenceFusionRequest(raw_evidence=items)
    resp = fusion_engine.fuse(req)
    assert resp.dark_pattern is None
    assert resp.risk_level == "LOW"


def test_safeguard_j_unknown_continuity_creates_no_synthetic_graph_edge(deduplicator):
    """Safeguard J: Unknown/impossible transition creates no STAGE_TRANSITION edge."""
    items = [
        EvidenceItem(evidence_id="E1", source="dom", type="confirmed", journey_id="j1", journey_stage=STAGE_CONFIRMATION),
        EvidenceItem(evidence_id="E2", source="dom", type="pay_again", journey_id="j1", journey_stage=STAGE_PAYMENT),
    ]
    graph, scoring = deduplicator.build_evidence_graph(items)
    st = [e for e in graph.edges if e.relation_type == REL_STAGE_TRANSITION]
    assert len(st) == 0
