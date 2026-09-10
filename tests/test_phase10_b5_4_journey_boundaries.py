"""tests/test_phase10_b5_4_journey_boundaries.py
Phase B5.4 Advanced Multi-Page Interaction Boundary & Context Engine Test Suite.

Validates the full deterministic Journey Boundary layer across:
A. Identity & Format (opaque immutable jrn_<uuid4 hex>)
B. Hierarchy & Invariants (session != journey != page != event)
C. Tab Isolation (simultaneous tabs cannot merge evidence)
D. Purchase Stage Progression (discovery -> product -> cart -> checkout -> payment -> confirmation)
E. Cancellation Stage Progression (subscription -> cancellation -> retention -> termination)
F. Same-site Different-product Isolation (catalog browsing vs price progression)
G. SPA Transitions (2-of-3 compound heuristic)
H. Auxiliary Contexts (privacy/terms/help sidecars, zero financial/contradiction/temporal pollution)
I. External Payment Gateway (suspension, no 3rd-party scraping, safe return)
J. Inactivity Policy (5-15 min soft idle, >=15 min hard expiration)
K. Terminal States (no silent resumption from completed/abandoned/expired/terminated)
L. Contradiction Boundary Gating
M. Temporal Boundary Gating
N. Legacy Fallback (B5.1-B5.3 backward compatibility)
O. Privacy Safeguards (no sensitive credentials/cards stored)
P. Bounded Storage & Deterministic Pruning (max 5 journeys/tab, max 20 events/journey)
Q. Adversarial Scenarios (all 30 required contract tests)
"""
from __future__ import annotations

import json
import subprocess
import uuid
import pytest

from backend.schemas import PredictResponse
from backend.schemas.evidence import (
    EvidenceFusionRequest,
    EvidenceItem,
    TemporalRelationshipItem,
    ContradictionItem,
)
from backend.schemas.price import PriceAnalysisResponse
from backend.services.evidence_fusion import EvidenceFusionEngine
from backend.services.journey_engine import (
    ALLOWED_STAGES,
    ALLOWED_STATUSES,
    JOURNEY_INACTIVITY_TIMEOUT_MS,
    JOURNEY_SOFT_IDLE_TIMEOUT_MS,
    MAX_ACTIVE_JOURNEYS_PER_TAB,
    MAX_EVENTS_PER_JOURNEY,
    STAGE_CART,
    STAGE_CHECKOUT,
    STAGE_CONFIRMATION,
    STAGE_DISCOVERY,
    STAGE_PAYMENT,
    STAGE_PRODUCT,
    STAGE_CANCELLATION,
    STAGE_RETENTION_STEP,
    STAGE_SUBSCRIPTION,
    STAGE_TERMINATION,
    STAGE_UNKNOWN,
    STATUS_ABANDONED,
    STATUS_ACTIVE,
    STATUS_COMPLETED,
    STATUS_EXPIRED_INACTIVE,
    STATUS_IDLE,
    STATUS_SUSPENDED,
    STATUS_SUSPENDED_EXTERNAL_GATEWAY,
    STATUS_TERMINATED,
    TERMINAL_STATUSES,
    JourneyEngine,
    JourneyState,
    extract_site_identity,
    make_journey_id,
)

fusion_engine = EvidenceFusionEngine()


def run_node_journey_manager_code(js_code: str) -> dict:
    """Helper to run code against DarkShield/extension/analyzer/journeyManager.js in Node."""
    wrapper = f"""
    const {{ JourneyManager, extractSiteIdentity, makeJourneyId }} = require('./DarkShield/extension/analyzer/journeyManager.js');
    {js_code}
    """
    res = subprocess.run(["node", "-e", wrapper], capture_output=True, text=True, check=True)
    return json.loads(res.stdout.strip()) if res.stdout.strip() else {}


# =====================================================================
# CATEGORY A: IDENTITY & FORMAT (Section 2 & 25.A)
# =====================================================================

def test_01_journey_id_format_and_prefix():
    """Verify journey_id follows jrn_<uuid4 hex> format."""
    jid = make_journey_id()
    assert jid.startswith("jrn_")
    hex_part = jid[4:]
    assert len(hex_part) == 32
    # Must be valid hex
    int(hex_part, 16)


def test_02_journey_id_uniqueness():
    """Verify journey IDs are statistically unique opaque UUIDs."""
    ids = {make_journey_id() for _ in range(100)}
    assert len(ids) == 100


def test_03_journey_id_no_semantic_attributes_embedded():
    """Verify journey_id does NOT embed tab_id, origin, intent, or stage."""
    jid = make_journey_id()
    for semantic in ["tab", "checkout", "http", "example.com", "cart"]:
        assert semantic not in jid


def test_04_js_journey_id_format_matches_backend():
    """Verify Node/JS JourneyManager generates identical jrn_<hex> format."""
    out = run_node_journey_manager_code("""
    const id = makeJourneyId();
    console.log(JSON.stringify({ id, valid: /^jrn_[0-9a-f]{32}$/.test(id) }));
    """)
    assert out["valid"] is True


# =====================================================================
# CATEGORY B: HIERARCHY & INVARIANTS (Section 1 & 25.B)
# =====================================================================

def test_05_hierarchy_invariants_distinct_identities():
    """Verify session_id != journey_id != page_load_id != event_id."""
    session_id = "sess_ext_12345"
    journey_id = make_journey_id()
    page_load_id = f"page_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_{uuid.uuid4().hex[:8]}"

    assert session_id != journey_id
    assert journey_id != page_load_id
    assert page_load_id != event_id
    assert journey_id != event_id


def test_06_site_identity_etld_plus_one_extraction():
    """Verify registrable domain / eTLD+1 extraction."""
    assert extract_site_identity("https://shop.example.com/checkout") == "example.com"
    assert extract_site_identity("https://secure.pay.example.com") == "example.com"
    assert extract_site_identity("https://checkout.example.co.uk/step1") == "example.co.uk"
    assert extract_site_identity("http://localhost:8000/cart") == "localhost"
    assert extract_site_identity("example.com") == "example.com"


# =====================================================================
# CATEGORY C: TAB ISOLATION (Section 7 & 25.C, Adversarial #4)
# =====================================================================

def test_07_tab_isolation_separate_journeys():
    """Verify two simultaneous checkout tabs receive distinct journeys."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j1 = jm.getOrCreateJourney(1, 'https://shop.example.com/checkout', 'sess_1');
    const j2 = jm.getOrCreateJourney(2, 'https://shop.example.com/checkout', 'sess_1');
    console.log(JSON.stringify({ j1: j1.journey_id, j2: j2.journey_id, same: j1.journey_id === j2.journey_id }));
    """)
    assert out["same"] is False
    assert out["j1"] != out["j2"]


def test_08_tab_isolation_fusion_rejection():
    """Evidence from Tab 1 (₹499) and Tab 2 (₹799) must never correlate."""
    item_tab1 = EvidenceItem(
        evidence_id="E001",
        source="price",
        type="displayed_price",
        description="Price in tab 1",
        value=499.0,
        journey_id="jrn_tab1_aaa",
        decision_context="checkout",
    )
    item_tab2 = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="price_change",
        description="Price change in tab 2",
        value=799.0,
        journey_id="jrn_tab2_bbb",
        decision_context="checkout",
    )
    assert JourneyEngine.are_in_same_journey(item_tab1, item_tab2) is False


def test_09_tab_isolation_no_shared_evidence():
    """Verify evidence cannot cross tab boundaries in fusion."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="dom",
        type="cancel_action_disabled",
        description="Disabled cancel button in tab 1",
        detected=True,
        strength="strong",
        journey_id="jrn_tab1",
        decision_context="cancellation",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="behavior",
        type="repeated_retention_interference",
        description="Retention interference in tab 2",
        detected=True,
        strength="strong",
        journey_id="jrn_tab2",
        decision_context="cancellation",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    # Must NOT form a corroborated multi-source group across tabs!
    for g in res.evidence_groups:
        assert not (item_a.evidence_id in g.evidence_ids and item_b.evidence_id in g.evidence_ids)


# =====================================================================
# CATEGORY D: PURCHASE STAGE PROGRESSION (Section 5 & 6, 25.D)
# =====================================================================

def test_10_valid_purchase_transitions():
    """Verify valid commercial progression stages."""
    valid_transitions = [
        (STAGE_DISCOVERY, STAGE_PRODUCT),
        (STAGE_PRODUCT, STAGE_CART),
        (STAGE_CART, STAGE_CHECKOUT),
        (STAGE_CHECKOUT, STAGE_PAYMENT),
        (STAGE_PAYMENT, STAGE_CONFIRMATION),
        (STAGE_CHECKOUT, STAGE_CHECKOUT),
    ]
    for b, a in valid_transitions:
        assert JourneyEngine.is_valid_stage_transition(b, a) is True


def test_11_invalid_purchase_backward_transitions():
    """Verify invalid/backwards transitions are rejected."""
    invalid_transitions = [
        (STAGE_CONFIRMATION, STAGE_PRODUCT),
        (STAGE_PAYMENT, STAGE_DISCOVERY),
        (STAGE_CONFIRMATION, STAGE_CHECKOUT),
    ]
    for b, a in invalid_transitions:
        assert JourneyEngine.is_valid_stage_transition(b, a) is False


def test_12_stage_assignment_in_journey_manager():
    """Verify JourneyManager assigns correct canonical stage based on route."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const s1 = jm.inferStageFromRoute('/product/item-123');
    const s2 = jm.inferStageFromRoute('/cart');
    const s3 = jm.inferStageFromRoute('/checkout/step2');
    const s4 = jm.inferStageFromRoute('/order/completed');
    console.log(JSON.stringify({ s1, s2, s3, s4 }));
    """)
    assert out["s1"] == STAGE_PRODUCT
    assert out["s2"] == STAGE_CART
    assert out["s3"] == STAGE_CHECKOUT
    assert out["s4"] == STAGE_CONFIRMATION


# =====================================================================
# CATEGORY E: CANCELLATION STAGE PROGRESSION (Section 5 & 6, 25.E)
# =====================================================================

def test_13_valid_cancellation_transitions():
    """Verify cancellation stages cycle legitimately."""
    valid = [
        (STAGE_SUBSCRIPTION, STAGE_CANCELLATION),
        (STAGE_CANCELLATION, STAGE_RETENTION_STEP),
        (STAGE_RETENTION_STEP, STAGE_CANCELLATION),
        (STAGE_CANCELLATION, STAGE_TERMINATION),
    ]
    for b, a in valid:
        assert JourneyEngine.is_valid_stage_transition(b, a) is True


def test_14_cancellation_to_purchase_invalid_progression():
    """Verify cancellation stage cannot transition directly into purchase confirmation."""
    assert JourneyEngine.is_valid_stage_transition(STAGE_CANCELLATION, STAGE_CONFIRMATION) is False


# =====================================================================
# CATEGORY F: SAME-SITE DIFFERENT-PRODUCT ISOLATION (Section 11, Adversarial #1 & #2)
# =====================================================================

def test_15_same_site_different_product_catalog_browsing():
    """Product A ₹499 -> Product B ₹799: must NOT produce price_change."""
    assert JourneyEngine.is_valid_stage_transition(STAGE_PRODUCT, STAGE_PRODUCT) is False


def test_16_temporal_engine_rejects_product_to_product_price_change():
    """Verify TemporalEngine rejects temporal relationship between two different products."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="price",
        type="displayed_price",
        description="Product A base price",
        value=499.0,
        temporal_position="before_action",
        journey_id="jrn_1",
        journey_stage=STAGE_PRODUCT,
        metadata={"product_anchor": "sku_101", "timestamp": 1000},
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="price_change",
        description="Product B price change",
        value=799.0,
        temporal_position="after_action",
        journey_id="jrn_1",
        journey_stage=STAGE_PRODUCT,
        metadata={"product_anchor": "sku_202", "timestamp": 2000},
    )
    p_analysis = PriceAnalysisResponse(
        previous_price=499.0,
        current_price=799.0,
        price_change=300.0,
        price_change_detected=True,
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(
        price_analysis=p_analysis,
        raw_evidence=[item_a, item_b],
    ))
    p_changes = [t for t in res.temporal_relationships if t.type == "price_change_after_action"]
    assert len(p_changes) == 0


def test_17_same_route_different_product_anchors_rejected():
    """Same route /product with different anchors rejects temporal coupling."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="price",
        type="displayed_price",
        description="Item A price",
        value=499.0,
        temporal_position="before_action",
        journey_id="jrn_1",
        journey_stage=STAGE_CHECKOUT,
        metadata={"product_anchor": "item_A", "timestamp": 1000},
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="additional_cost",
        description="Fee on item B",
        value=50.0,
        temporal_position="after_action",
        journey_id="jrn_1",
        journey_stage=STAGE_CHECKOUT,
        metadata={"product_anchor": "item_B", "timestamp": 2000},
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    fees = [t for t in res.temporal_relationships if t.type == "fee_added_after_action"]
    assert len(fees) == 0


# =====================================================================
# CATEGORY G: SPA TRANSITIONS (Section 14, Adversarial #13 & #14)
# =====================================================================

def test_18_spa_transition_requires_compound_signals():
    """SPA transition requires at least 2 of 3 signals (landmark, user action, form signature)."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://example.com/app', 'sess_1');
    
    // 1 signal only: DOM mutation alone -> REJECTED
    const t1 = jm.evaluateSPATransition(j, { domLandmarkChanged: true, userAction: false, formSignatureChanged: false });
    
    // 2 signals: Landmark + User Action -> ACCEPTED
    const t2 = jm.evaluateSPATransition(j, { domLandmarkChanged: true, userAction: true, formSignatureChanged: false });
    
    console.log(JSON.stringify({ t1, t2 }));
    """)
    assert out["t1"] is False
    assert out["t2"] is True


def test_19_spa_rerender_debounce_duplicate_suppression():
    """SPA re-renders within 1.5s settle window do not create duplicate stage transitions."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://example.com/app', 'sess_1');
    
    const now = 10000;
    const t1 = jm.recordSPATransition(j, 'CHECKOUT', { domLandmarkChanged: true, userAction: true }, now);
    // Rapid duplicate re-render at +500ms
    const t2 = jm.recordSPATransition(j, 'CHECKOUT', { domLandmarkChanged: true, userAction: true }, now + 500);
    
    console.log(JSON.stringify({ t1, t2, historyLength: j.stage_history.length }));
    """)
    assert out["t1"] is True
    assert out["t2"] is False
    assert out["historyLength"] == 1


# =====================================================================
# CATEGORY H: AUXILIARY CONTEXTS (Section 12, Adversarial #9-#11)
# =====================================================================

def test_20_auxiliary_context_creation_and_suspension():
    """Privacy/Terms page opens sidecar context and suspends active merchant journey."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://shop.example.com/checkout', 'sess_1');
    
    // Navigate to privacy page in same tab
    const aux = jm.handleAuxiliaryNavigation(1, 'https://shop.example.com/privacy', 'sess_1');
    
    console.log(JSON.stringify({
        parentStatus: j.status,
        isAuxiliary: aux.is_auxiliary,
        parentJourneyId: aux.parent_journey_id
    }));
    """)
    assert out["parentStatus"] == STATUS_SUSPENDED
    assert out["isAuxiliary"] is True
    assert out["parentJourneyId"] is not None


def test_21_auxiliary_evidence_rejected_from_financial_impact():
    """Auxiliary evidence does NOT participate in financial impact or consequences."""
    aux_item = EvidenceItem(
        evidence_id="E_AUX_001",
        source="price",
        type="displayed_price",
        description="Auxiliary pricing info in terms modal",
        value=199.0,
        is_auxiliary=True,
    )
    p_analysis = PriceAnalysisResponse(displayed_price={"amount": 199.0, "currency": "INR"})
    res = fusion_engine.fuse(EvidenceFusionRequest(price_analysis=p_analysis, raw_evidence=[aux_item]))
    assert res.financial_impact is None
    assert res.consumer_consequence is None


def test_22_auxiliary_evidence_excluded_from_contradictions():
    """Auxiliary items NEVER participate in commercial contradiction escalation."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="text",
        type="easy_cancel",
        description="Cancel easily online anytime.",
        decision_context="cancellation",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="dom",
        type="cancel_action_disabled",
        description="Disabled cancel button on terms FAQ",
        detected=True,
        strength="strong",
        decision_context="cancellation",
        is_auxiliary=True,
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    assert len(res.contradictions) == 0


def test_23_auxiliary_evidence_excluded_from_temporal_engine():
    """Auxiliary items NEVER participate in temporal transitions."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="price",
        type="displayed_price",
        description="Initial price",
        value=499.0,
        temporal_position="before_action",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="additional_cost",
        description="Auxiliary fee example",
        value=50.0,
        temporal_position="after_action",
        is_auxiliary=True,
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    assert len(res.temporal_relationships) == 0


# =====================================================================
# CATEGORY I: EXTERNAL PAYMENT GATEWAY (Section 13, Adversarial #15-#17)
# =====================================================================

def test_24_external_payment_gateway_suspends_journey():
    """Navigating to external payment gateway sets SUSPENDED_EXTERNAL_GATEWAY."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://merchant.example.com/checkout', 'sess_1');
    const res = jm.handleExternalGatewayNavigation(1, 'https://securepay.thirdparty.com/pay');
    console.log(JSON.stringify({ status: j.status, suspended: res.suspended }));
    """)
    assert out["status"] == STATUS_SUSPENDED_EXTERNAL_GATEWAY
    assert out["suspended"] is True


def test_25_external_payment_gateway_resume_on_safe_return():
    """Returning safely to merchant confirmation resumes merchant journey."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://merchant.example.com/checkout', 'sess_1');
    jm.handleExternalGatewayNavigation(1, 'https://securepay.thirdparty.com/pay');
    
    // Return to merchant
    const resumed = jm.resumeFromGatewayReturn(1, 'https://merchant.example.com/payment/return');
    console.log(JSON.stringify({ status: j.status, resumed: !!resumed }));
    """)
    assert out["status"] == STATUS_ACTIVE
    assert out["resumed"] is True


def test_26_external_payment_gateway_unrelated_site_does_not_resume():
    """Navigating to an unrelated site after gateway does not silently resume."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://merchant.example.com/checkout', 'sess_1');
    jm.handleExternalGatewayNavigation(1, 'https://securepay.thirdparty.com/pay');
    
    // Unrelated site
    const resumed = jm.resumeFromGatewayReturn(1, 'https://completely-different-news.com');
    console.log(JSON.stringify({ status: j.status, resumed: !!resumed }));
    """)
    assert out["status"] == STATUS_SUSPENDED_EXTERNAL_GATEWAY
    assert out["resumed"] is False


# =====================================================================
# CATEGORY J: INACTIVITY POLICY (Section 9, Adversarial #18 & #19)
# =====================================================================

def test_27_inactivity_soft_idle_between_5_and_15_minutes():
    """Inactivity 5-15 min sets status IDLE."""
    last_event = 1000.0
    now_8min = last_event + (8 * 60 * 1000)
    status = JourneyEngine.evaluate_inactivity_status(last_event, now_8min)
    assert status == STATUS_IDLE


def test_28_inactivity_hard_expiry_at_or_over_15_minutes():
    """Inactivity >= 15 min sets status EXPIRED_INACTIVE."""
    last_event = 1000.0
    now_15min = last_event + JOURNEY_INACTIVITY_TIMEOUT_MS
    status = JourneyEngine.evaluate_inactivity_status(last_event, now_15min)
    assert status == STATUS_EXPIRED_INACTIVE


def test_29_inactivity_new_journey_created_after_expiry():
    """Interaction after 15 min creates a brand NEW journey."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j1 = jm.getOrCreateJourney(1, 'https://example.com/shop', 'sess_1', 1000);
    
    // Simulate interaction 16 minutes later
    const j2 = jm.getOrCreateJourney(1, 'https://example.com/shop', 'sess_1', 1000 + (16 * 60 * 1000));
    
    console.log(JSON.stringify({
        j1_id: j1.journey_id,
        j2_id: j2.journey_id,
        isNew: j1.journey_id !== j2.journey_id
    }));
    """)
    assert out["isNew"] is True
    assert out["j1_id"] != out["j2_id"]


# =====================================================================
# CATEGORY K: TERMINAL STATES & NON-RESUMPTION (Section 22, Adversarial #6-#8)
# =====================================================================

def test_30_terminal_statuses_defined():
    """Verify terminal statuses set."""
    for s in [STATUS_COMPLETED, STATUS_ABANDONED, STATUS_EXPIRED_INACTIVE, STATUS_TERMINATED]:
        assert s in TERMINAL_STATUSES


def test_31_completed_journey_does_not_silently_resume():
    """Completed purchase followed by new action creates new journey."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j1 = jm.getOrCreateJourney(1, 'https://example.com/shop', 'sess_1');
    jm.completeJourney(j1.journey_id);
    
    const j2 = jm.getOrCreateJourney(1, 'https://example.com/shop', 'sess_1');
    console.log(JSON.stringify({
        j1_status: j1.status,
        isNew: j1.journey_id !== j2.journey_id
    }));
    """)
    assert out["j1_status"] == STATUS_COMPLETED
    assert out["isNew"] is True


def test_32_terminated_cancellation_does_not_resume():
    """Terminated subscription cancellation does not resume upon new visit."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j1 = jm.getOrCreateJourney(1, 'https://example.com/cancel', 'sess_1');
    jm.terminateJourney(j1.journey_id);
    
    const j2 = jm.getOrCreateJourney(1, 'https://example.com/shop', 'sess_1');
    console.log(JSON.stringify({
        j1_status: j1.status,
        isNew: j1.journey_id !== j2.journey_id
    }));
    """)
    assert out["j1_status"] == STATUS_TERMINATED
    assert out["isNew"] is True


# =====================================================================
# CATEGORY L: CONTRADICTION GATING (Section 18, Adversarial #23 & #27)
# =====================================================================

def test_33_contradiction_requires_matching_journey():
    """Evidence with different journey_ids NEVER generates contradiction."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="text",
        type="subscription_trap",
        description="Cancel anytime with one click.",
        decision_context="cancellation",
        journey_id="jrn_aaa",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="dom",
        type="cancel_action_disabled",
        description="Disabled cancel button",
        detected=True,
        strength="strong",
        decision_context="cancellation",
        journey_id="jrn_bbb",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    assert len(res.contradictions) == 0


def test_34_contradiction_emitted_when_same_journey_and_compatible_context():
    """Matching journey and compatible context detects valid contradiction."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="text",
        type="subscription_trap",
        description="Cancel anytime online without penalty.",
        decision_context="cancellation",
        journey_id="jrn_shared_123",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="dom",
        type="cancel_action_disabled",
        description="Disabled cancel button on cancel page",
        detected=True,
        strength="strong",
        decision_context="cancellation",
        journey_id="jrn_shared_123",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    assert len(res.contradictions) >= 1
    assert res.contradictions[0].pattern == "obstruction"


def test_35_contradiction_rejected_for_same_journey_incompatible_context():
    """Same journey with conflicting contexts (checkout vs cancellation) rejects contradiction."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="text",
        type="subscription_trap",
        description="Cancel anytime online.",
        decision_context="cancellation",
        journey_id="jrn_shared_123",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="dom",
        type="preselected_option",
        description="Preselected commercial option",
        detected=True,
        strength="strong",
        decision_context="checkout",
        journey_id="jrn_shared_123",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    assert len(res.contradictions) == 0


# =====================================================================
# CATEGORY M: TEMPORAL GATING (Section 19, Adversarial #24 & #28)
# =====================================================================

def test_36_temporal_engine_requires_matching_journey():
    """Different journey IDs cannot form temporal relationship."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="price",
        type="displayed_price",
        description="First journey displayed price",
        value=499.0,
        temporal_position="before_action",
        journey_id="jrn_first",
        decision_context="checkout",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="additional_cost",
        description="Second journey fee",
        value=50.0,
        temporal_position="after_action",
        journey_id="jrn_second",
        decision_context="checkout",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    assert len(res.temporal_relationships) == 0


def test_37_temporal_engine_valid_same_journey_progression():
    """Matching journey with valid stage progression forms temporal relationship."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="price",
        type="displayed_price",
        description="Cart price",
        value=499.0,
        temporal_position="before_action",
        journey_id="jrn_valid",
        journey_stage=STAGE_CART,
        decision_context="checkout",
        metadata={"timestamp": 1000},
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="additional_cost",
        description="Fee at checkout",
        value=50.0,
        temporal_position="after_action",
        journey_id="jrn_valid",
        journey_stage=STAGE_CHECKOUT,
        decision_context="checkout",
        metadata={"timestamp": 2000},
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    fees = [t for t in res.temporal_relationships if t.type == "fee_added_after_action"]
    assert len(fees) == 1
    assert fees[0].strength == "strong"


# =====================================================================
# CATEGORY N: LEGACY FALLBACK (Section 20, Adversarial #22)
# =====================================================================

def test_38_legacy_fallback_when_journey_id_absent():
    """Preserve B5.1-B5.3 behavior when evidence items have no journey_id."""
    item_a = EvidenceItem(
        evidence_id="E001",
        source="price",
        type="displayed_price",
        description="Base price without journey",
        value=100.0,
        temporal_position="before_action",
        decision_context="checkout",
    )
    item_b = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="additional_cost",
        description="Fee without journey",
        value=20.0,
        temporal_position="after_action",
        decision_context="checkout",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_a, item_b]))
    assert len(res.temporal_relationships) == 1


def test_39_legacy_text_and_price_analysis_fallback():
    """Text prediction + Price analysis without journey_id works seamlessly."""
    t_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.9,
        model_version="v1.0.0",
        pattern_category="Drip Pricing",
        evidence="Processing fee added at checkout.",
    )
    p_analysis = PriceAnalysisResponse(
        displayed_price={"amount": 500.0, "currency": "INR"},
        additional_cost=50.0,
        late_disclosed=True,
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(text_prediction=t_pred, price_analysis=p_analysis))
    assert res.risk_level in ("MEDIUM", "HIGH", "CRITICAL")
    assert res.primary_pattern in ("Drip Pricing", "Price Disclosure Risk")


# =====================================================================
# CATEGORY O: PRIVACY SAFEGUARDS (Section 24, Adversarial #30)
# =====================================================================

def test_40_privacy_no_sensitive_fields_in_journey_state():
    """Verify JourneyState schema does not define or allow sensitive credentials."""
    sensitive_keys = {"password", "card", "cvv", "token", "ssn", "pin", "email", "phone"}
    fields = set(JourneyState.model_fields.keys())
    assert len(sensitive_keys.intersection(fields)) == 0


def test_41_privacy_sanitized_event_storage():
    """Verify JourneyManager sanitizes events and strips raw form values."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://example.com/checkout', 'sess_1');
    
    // Add event containing potentially sensitive raw inputs
    jm.recordEvent(j.journey_id, {
        type: 'INPUT',
        targetTag: 'input',
        password: 'my_secret_password',
        cardNumber: '4111222233334444',
        cvv: '123',
        safeMeta: 'ok'
    });
    
    const events = jm.getEvents(j.journey_id);
    const stored = events[0] || {};
    console.log(JSON.stringify({
        storedKeys: Object.keys(stored),
        hasPassword: 'password' in stored,
        hasCard: 'cardNumber' in stored,
        hasCvv: 'cvv' in stored
    }));
    """)
    assert out["hasPassword"] is False
    assert out["hasCard"] is False
    assert out["hasCvv"] is False


# =====================================================================
# CATEGORY P: BOUNDED STORAGE & PRUNING (Section 23, Adversarial #20 & #21)
# =====================================================================

def test_42_bounded_storage_max_5_journeys_per_tab():
    """Verify maximum 5 active/suspended journeys per tab via deterministic pruning."""
    out = run_node_journey_manager_code(f"""
    const jm = new JourneyManager();
    for (let i = 0; i < 10; i++) {{
        jm.getOrCreateJourney(1, 'https://site' + i + '.com', 'sess_1', i * 1000);
    }}
    const tabJourneys = jm.getJourneysForTab(1);
    console.log(JSON.stringify({{ count: tabJourneys.length, max: {MAX_ACTIVE_JOURNEYS_PER_TAB} }}));
    """)
    assert out["count"] <= MAX_ACTIVE_JOURNEYS_PER_TAB


def test_43_bounded_storage_max_20_events_per_journey():
    """Verify maximum 20 interaction events retained per journey."""
    out = run_node_journey_manager_code(f"""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://example.com', 'sess_1');
    for (let i = 0; i < 35; i++) {{
        jm.recordEvent(j.journey_id, {{ type: 'CLICK', index: i }});
    }}
    const events = jm.getEvents(j.journey_id);
    console.log(JSON.stringify({{ count: events.length, max: {MAX_EVENTS_PER_JOURNEY} }}));
    """)
    assert out["count"] == MAX_EVENTS_PER_JOURNEY


# =====================================================================
# CATEGORY Q: ALL REMAINING ADVERSARIAL CASES (Section 26)
# =====================================================================

def test_44_adversarial_same_route_different_intent():
    """Same route /account with different intent (PROFILE vs CANCELLATION)."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j1 = jm.getOrCreateJourney(1, 'https://example.com/account', 'sess_1', 1000, { intent: 'PROFILE' });
    const j2 = jm.getOrCreateJourney(1, 'https://example.com/account', 'sess_1', 2000, { intent: 'CANCELLATION' });
    console.log(JSON.stringify({ isDifferent: j1.journey_id !== j2.journey_id }));
    """)
    assert out["isDifferent"] is True


def test_45_adversarial_same_origin_separate_journeys():
    """Same origin creates distinct journeys across tabs."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const jA = jm.getOrCreateJourney(10, 'https://myshop.com/item/1', 'sess_1');
    const jB = jm.getOrCreateJourney(20, 'https://myshop.com/item/2', 'sess_1');
    console.log(JSON.stringify({ distinct: jA.journey_id !== jB.journey_id }));
    """)
    assert out["distinct"] is True


def test_46_adversarial_terms_and_help_pages_during_checkout():
    """Terms and Help pages open as auxiliary context during checkout."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://shop.com/checkout', 'sess_1');
    const auxTerms = jm.handleAuxiliaryNavigation(1, 'https://shop.com/terms', 'sess_1');
    const auxHelp = jm.handleAuxiliaryNavigation(1, 'https://shop.com/help', 'sess_1');
    console.log(JSON.stringify({
        termsAux: auxTerms.is_auxiliary,
        helpAux: auxHelp.is_auxiliary
    }));
    """)
    assert out["termsAux"] is True
    assert out["helpAux"] is True


def test_47_adversarial_unknown_context_between_checkout_stages():
    """Unknown context between checkout stages handled conservatively."""
    assert JourneyEngine.is_valid_stage_transition(STAGE_UNKNOWN, STAGE_CHECKOUT) is True
    assert JourneyEngine.is_valid_stage_transition(STAGE_CHECKOUT, STAGE_UNKNOWN) is True


def test_48_adversarial_gateway_timeout_and_expiration():
    """External payment gateway left inactive for > 15 minutes expires."""
    out = run_node_journey_manager_code("""
    const jm = new JourneyManager();
    const j = jm.getOrCreateJourney(1, 'https://merchant.com/checkout', 'sess_1', 1000);
    jm.handleExternalGatewayNavigation(1, 'https://gateway.com/pay', 1000);
    
    // 20 minutes later
    const status = jm.evaluateStatus(j.journey_id, 1000 + (20 * 60 * 1000));
    console.log(JSON.stringify({ status }));
    """)
    assert out["status"] == STATUS_EXPIRED_INACTIVE


def test_49_adversarial_missing_product_anchor_does_not_invent_identity():
    """When product identity is unobservable, product_anchor is null, never fabricated."""
    j = JourneyState(journey_id=make_journey_id())
    assert j.product_anchor is None


def test_50_adversarial_no_evidence_crossing_tab_boundary():
    """Evidence items across tabs with identical routes never merge."""
    item_tab1 = EvidenceItem(
        evidence_id="E001",
        source="dom",
        type="action_size_asymmetry",
        description="Asymmetry on tab 1",
        detected=True,
        strength="strong",
        journey_id="jrn_tab_1",
    )
    item_tab2 = EvidenceItem(
        evidence_id="E002",
        source="behavior",
        type="retention_friction",
        description="Friction on tab 2",
        detected=True,
        strength="strong",
        journey_id="jrn_tab_2",
    )
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=[item_tab1, item_tab2]))
    # Each item forms its own uncorroborated group
    for g in res.evidence_groups:
        assert len(g.sources) == 1
        assert g.corroborated is False


def test_51_adversarial_global_risk_clamp_preserved():
    """Score remains clamped strictly in [0.0, 10.0]."""
    items = [
        EvidenceItem(
            evidence_id=f"E{i:03d}",
            source="dom" if i % 2 == 0 else "behavior",
            type="cancel_action_disabled",
            description=f"Evidence item {i}",
            detected=True,
            strength="strong",
            journey_id="jrn_heavy",
            decision_context="cancellation",
        )
        for i in range(20)
    ]
    res = fusion_engine.fuse(EvidenceFusionRequest(raw_evidence=items))
    assert 0.0 <= res.risk_score <= 10.0


def test_52_adversarial_risk_thresholds_exact():
    """Preserve B5.2 risk-level thresholds: LOW < 3.0, MEDIUM >= 3.0, HIGH >= 5.0, CRITICAL >= 8.0."""
    from backend.services.evidence_fusion import (
        RISK_THRESHOLD_MEDIUM,
        RISK_THRESHOLD_HIGH,
        RISK_THRESHOLD_CRITICAL,
    )
    assert RISK_THRESHOLD_MEDIUM == 3.0
    assert RISK_THRESHOLD_HIGH == 5.0
    assert RISK_THRESHOLD_CRITICAL == 8.0
