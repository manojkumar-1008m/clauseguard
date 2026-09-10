"""tests/test_phase10_evidence_contract.py
Phase B5.1: Unified Evidence Contract & Source-Scoped Context Test Suite.

Validates:
PART 15: Schema Validation
- Text evidence, Price evidence, Behavior evidence, DOM evidence, Image evidence
- Missing optional fields & default values
- Invalid source, strength, temporal_position, decision_context
- Model confidence boundaries
- Backward-compatible legacy confidence

PART 16: Source-Scoped Context Tests
- TEST A: Text requires_context=True + DOM strong evidence -> DOM preserved
- TEST B: Text requires_context=True + Behavior strong evidence -> Behavior preserved
- TEST C: Text requires_context=True + Price renewal_price -> Price preserved
- TEST D: Text requires_context=True + Image evidence -> Image preserved
- TEST E: Text requires_context=True + No other evidence -> Context-required remains

PART 13 & 14: Structured Provenance & Deduplication
- Structured provenance serialization & source validation
- Anti-double-counting without using model confidence in key
"""
import pytest
from backend.schemas import PredictResponse
from backend.schemas.evidence import (
    ALLOWED_DECISION_CONTEXTS,
    ALLOWED_SOURCES,
    ALLOWED_STRENGTHS,
    ALLOWED_TEMPORAL_POSITIONS,
    EvidenceFusionRequest,
    EvidenceItem,
    StructuredProvenance,
)
from backend.schemas.price import DisplayedPrice, PriceAnalysisResponse, PriceEntity
from backend.services.evidence_adapters import (
    adapt_behavior_evidence,
    adapt_dom_evidence,
    adapt_image_evidence,
    adapt_price_analysis,
    adapt_text_prediction,
)
from backend.services.evidence_fusion import EvidenceFusionEngine

fusion_engine = EvidenceFusionEngine()


# ==============================================================================
# PART 15: SCHEMA VALIDATION TESTS
# ==============================================================================

def test_01_text_evidence_schema():
    """1. Validate Text Evidence with model_confidence, strength, and offsets."""
    item = EvidenceItem(
        evidence_id="E001",
        source="text",
        type="subscription_trap",
        pattern="subscription_trap",
        description="Membership renews automatically",
        detected=True,
        strength="strong",
        model_confidence=0.92,
        character_start=15,
        character_end=45,
        temporal_position="static",
        decision_context="subscription",
        provenance="ClauseGuard-Text-V3",
    )
    assert item.source == "text"
    assert item.model_confidence == 0.92
    assert item.strength == "strong"
    assert item.character_start == 15
    assert item.temporal_position == "static"
    assert item.decision_context == "subscription"


def test_02_price_evidence_schema_deterministic():
    """2. Validate Price Evidence: deterministic with strength='strong' and model_confidence=None."""
    item = EvidenceItem(
        evidence_id="E002",
        source="price",
        type="renewal_price",
        pattern="subscription_trap",
        description="Renewal price of ₹999/month",
        value=999.0,
        currency="INR",
        detected=True,
        strength="strong",
        model_confidence=None,  # Deterministic: MUST NOT fabricate fake ML confidence
        confidence=0.95,  # Legacy field
        temporal_position="static",
        decision_context="subscription",
        provenance="price_analyzer",
    )
    assert item.source == "price"
    assert item.model_confidence is None
    assert item.strength == "strong"
    assert item.value == 999.0
    assert item.currency == "INR"
    assert item.confidence == 0.95


def test_03_behavior_evidence_schema():
    """3. Validate Behavior Evidence with event_indices and route_sequence."""
    item = EvidenceItem(
        evidence_id="E003",
        source="behavior",
        type="cancellation_obstruction",
        description="Cancellation flow encountered multiple retention walls",
        detected=True,
        strength="strong",
        event_indices=[2, 5, 8],
        route="/cancel",
        route_sequence=["/home", "/account", "/cancel"],
        decision_context="cancellation",
        temporal_position="during_action",
        provenance="behavior_sequence_b3",
    )
    assert item.source == "behavior"
    assert item.event_indices == [2, 5, 8]
    assert item.route_sequence == ["/home", "/account", "/cancel"]
    assert item.decision_context == "cancellation"
    assert item.temporal_position == "during_action"


def test_04_dom_evidence_schema():
    """4. Validate DOM Evidence with element_ref and after_action temporal position."""
    item = EvidenceItem(
        evidence_id="E004",
        source="dom",
        type="post_action_fee_added",
        description="Mandatory fee of $15 added after checkout click",
        element_ref="#order-summary-fee",
        event_indices=[4],
        route="/checkout",
        decision_context="checkout",
        temporal_position="after_action",
        strength="strong",
        metadata={"fee_amount": 15.0},
    )
    assert item.source == "dom"
    assert item.element_ref == "#order-summary-fee"
    assert item.temporal_position == "after_action"
    assert item.metadata["fee_amount"] == 15.0


def test_05_future_image_evidence_schema():
    """5. Validate Future Image Evidence with bounding_box and ML detector confidence."""
    item = EvidenceItem(
        evidence_id="E005",
        source="image",
        type="countdown_timer",
        description="Visual countdown timer detected in header",
        detected=True,
        model_confidence=0.91,  # ML detector confidence
        strength="strong",
        bounding_box={"x": 120, "y": 45, "width": 200, "height": 50},
        frame_id="frame_001",
        temporal_position="static",
        provenance="image_analyzer",
    )
    assert item.source == "image"
    assert item.model_confidence == 0.91
    assert item.bounding_box == {"x": 120, "y": 45, "width": 200, "height": 50}
    assert item.frame_id == "frame_001"


def test_06_missing_optional_fields_defaults():
    """6. Validate minimal EvidenceItem with all optional fields defaulting safely."""
    item = EvidenceItem(
        evidence_id="E006",
        source="text",
        type="urgency",
        description="Limited time offer",
    )
    assert item.detected is True
    assert item.strength is None
    assert item.model_confidence is None
    assert item.confidence is None
    assert item.element_ref is None
    assert item.event_indices == []
    assert item.route is None
    assert item.route_sequence == []
    assert item.decision_context is None
    assert item.temporal_position is None
    assert item.bounding_box is None
    assert item.frame_id is None
    assert item.metadata == {}


def test_07_invalid_source_rejected():
    """7. Validate that unsupported source names are rejected."""
    with pytest.raises(ValueError, match="Invalid source"):
        EvidenceItem(
            evidence_id="E007",
            source="unknown_magic_source",
            type="test",
            description="test description",
        )


def test_08_invalid_strength_rejected():
    """8. Validate that invalid strength strings are rejected."""
    with pytest.raises(ValueError, match="Invalid strength"):
        EvidenceItem(
            evidence_id="E008",
            source="dom",
            type="disabled_action",
            description="Button disabled",
            strength="extremely_high",  # Must be weak, moderate, strong, or insufficient
        )


def test_09_invalid_temporal_position_rejected():
    """9. Validate that invalid temporal positions are rejected."""
    with pytest.raises(ValueError, match="Invalid temporal_position"):
        EvidenceItem(
            evidence_id="E009",
            source="price",
            type="additional_cost",
            description="Fee added",
            temporal_position="yesterday",
        )


def test_10_invalid_decision_context_rejected():
    """10. Validate that arbitrary unlisted decision contexts are rejected."""
    with pytest.raises(ValueError, match="Invalid decision_context"):
        EvidenceItem(
            evidence_id="E010",
            source="dom",
            type="confirmation_ui",
            description="Dialog opened",
            decision_context="arbitrary_uncontrolled_context",
        )


def test_11_model_confidence_range_validation():
    """11. Validate that model_confidence must strictly be within [0.0, 1.0]."""
    with pytest.raises(ValueError, match="model_confidence must be between 0.0 and 1.0"):
        EvidenceItem(
            evidence_id="E011",
            source="text",
            type="urgency",
            description="Urgency claim",
            model_confidence=1.25,
        )

    with pytest.raises(ValueError, match="model_confidence must be between 0.0 and 1.0"):
        EvidenceItem(
            evidence_id="E011",
            source="text",
            type="urgency",
            description="Urgency claim",
            model_confidence=-0.05,
        )


def test_12_backward_compatible_legacy_confidence():
    """12. Validate that legacy confidence field functions as expected without error."""
    item = EvidenceItem(
        evidence_id="E012",
        source="text",
        type="urgency",
        description="Legacy item",
        confidence=0.75,
    )
    assert item.confidence == 0.75
    assert item.model_confidence is None


# ==============================================================================
# PART 16: SOURCE-SCOPED CONTEXT TESTS
# ==============================================================================

def test_16_test_a_text_requires_context_dom_strong_preserved():
    """TEST A: Text requires_context = true + DOM strong evidence = true -> DOM preserved."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.55,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Obstruction",
        evidence="Cancel anytime in account settings",
    )
    dom_item = EvidenceItem(
        evidence_id="E_DOM_1",
        source="dom",
        type="cancel_action_disabled",
        description="Cancellation action button is disabled in DOM",
        detected=True,
        strength="strong",
        element_ref="BTN_CANCEL",
        decision_context="cancellation",
        temporal_position="during_action",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, dom_evidence=[dom_item])
    res = fusion_engine.fuse(req)

    # Source-scoped context requirements
    assert res.context_requirements["text"] is True
    assert res.context_requirements["dom"] is False

    # DOM evidence must be preserved
    dom_evidence = [e for e in res.evidence if e.source == "dom"]
    assert len(dom_evidence) >= 1
    assert dom_evidence[0].strength == "strong"
    assert dom_evidence[0].element_ref == "BTN_CANCEL"


def test_16_test_b_text_requires_context_behavior_strong_preserved():
    """TEST B: Text requires_context = true + Behavior strong evidence = true -> Behavior preserved."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.50,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Obstruction",
        evidence="Easy cancellation",
    )
    behavior_item = EvidenceItem(
        evidence_id="E_BEH_1",
        source="behavior",
        type="cancellation_obstruction",
        description="User traversed 4 repeated retention offers without confirmation",
        detected=True,
        strength="strong",
        event_indices=[1, 3, 5, 7],
        route_sequence=["/cancel_step1", "/cancel_step2", "/cancel_step3"],
        decision_context="cancellation",
        temporal_position="during_action",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, behavior_evidence=[behavior_item])
    res = fusion_engine.fuse(req)

    assert res.context_requirements["text"] is True
    assert res.context_requirements["behavior"] is False

    beh_evidence = [e for e in res.evidence if e.source == "behavior"]
    assert len(beh_evidence) >= 1
    assert beh_evidence[0].strength == "strong"
    assert beh_evidence[0].event_indices == [1, 3, 5, 7]
    assert beh_evidence[0].route_sequence == ["/cancel_step1", "/cancel_step2", "/cancel_step3"]


def test_16_test_c_text_requires_context_price_preserved():
    """TEST C: Text requires_context = true + Price renewal_price -> Price preserved."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.60,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Subscription",
        evidence="Membership continues",
    )
    price_resp = PriceAnalysisResponse(
        renewal_price=999.0,
        renewal_currency="INR",
        billing_period="month",
        recurring=True,
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, price_analysis=price_resp)
    res = fusion_engine.fuse(req)

    assert res.context_requirements["text"] is True
    assert res.context_requirements["price"] is False

    price_evidence = [e for e in res.evidence if e.source == "price" and e.type == "renewal_price"]
    assert len(price_evidence) == 1
    assert price_evidence[0].value == 999.0
    assert price_evidence[0].strength == "strong"
    assert price_evidence[0].model_confidence is None


def test_16_test_d_text_requires_context_image_preserved():
    """TEST D: Text requires_context = true + Image evidence exists -> Image preserved."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.52,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Urgency",
        evidence="Limited deal",
    )
    image_item = EvidenceItem(
        evidence_id="E_IMG_1",
        source="image",
        type="countdown_timer",
        description="Visual countdown timer component in viewport",
        detected=True,
        model_confidence=0.88,
        strength="strong",
        bounding_box={"x": 50, "y": 100, "width": 180, "height": 60},
    )
    req = EvidenceFusionRequest(text_prediction=text_pred, image_evidence=[image_item])
    res = fusion_engine.fuse(req)

    assert res.context_requirements["text"] is True
    assert res.context_requirements["image"] is False

    img_evidence = [e for e in res.evidence if e.source == "image"]
    assert len(img_evidence) >= 1
    assert img_evidence[0].model_confidence == 0.88
    assert img_evidence[0].bounding_box == {"x": 50, "y": 100, "width": 180, "height": 60}


def test_16_test_e_text_requires_context_no_other_evidence():
    """TEST E: Text requires_context = true + No other evidence -> Text conclusion remains context-required."""
    text_pred = PredictResponse(
        prediction=1,
        label="potential_dark_pattern",
        confidence=0.55,
        model_version="ClauseGuard-Text-V3",
        requires_context=True,
        pattern_category="Urgency",
        evidence="Offer expiring soon",
    )
    req = EvidenceFusionRequest(text_prediction=text_pred)
    res = fusion_engine.fuse(req)

    assert res.context_requirements["text"] is True
    assert res.requires_context is True
    assert res.dark_pattern is None
    assert res.risk_level == "LOW"


# ==============================================================================
# PART 13: STRUCTURED PROVENANCE TESTS
# ==============================================================================

def test_13_structured_provenance():
    """Validate StructuredProvenance schema and source validation."""
    prov = StructuredProvenance(
        source="dom",
        model_version="DarkShield-B4.4",
        timestamp=1710000000.5,
        page_load_id="page_load_abc",
        session_id="session_xyz",
        tab_id=42,
        frame_id="frame_0",
    )
    assert prov.source == "dom"
    assert prov.model_version == "DarkShield-B4.4"
    assert prov.tab_id == 42

    item = EvidenceItem(
        evidence_id="E013",
        source="dom",
        type="asymmetric_confirmation",
        description="Confirmation dialog has unequal choices",
        provenance=prov,
    )
    assert item.provenance.source == "dom"
    assert item.provenance.session_id == "session_xyz"


def test_13_structured_provenance_invalid_source():
    """Validate that StructuredProvenance rejects invalid source."""
    with pytest.raises(ValueError, match="Invalid provenance source"):
        StructuredProvenance(source="unsupported_source_subsystem")


# ==============================================================================
# PART 8–12 & 14: ADAPTERS AND DEDUPLICATION TESTS
# ==============================================================================

def test_14_deduplication_preserves_distinct_element_refs():
    """Validate deduplication preserves DOM items on different elements without using confidence."""
    item1 = EvidenceItem(
        evidence_id="E1",
        source="dom",
        type="cancel_action_visually_deemphasized",
        description="Cancel button deemphasized",
        element_ref="BTN_CANCEL_1",
    )
    item2 = EvidenceItem(
        evidence_id="E2",
        source="dom",
        type="cancel_action_visually_deemphasized",
        description="Cancel link deemphasized",
        element_ref="LINK_CANCEL_2",
    )
    req = EvidenceFusionRequest(dom_evidence=[item1, item2])
    res = fusion_engine.fuse(req)

    dom_items = [e for e in res.evidence if e.source == "dom"]
    assert len(dom_items) == 2
    assert {e.element_ref for e in dom_items} == {"BTN_CANCEL_1", "LINK_CANCEL_2"}


def test_14_deduplication_removes_exact_duplicates():
    """Validate deduplication eliminates exact duplicate items."""
    item1 = EvidenceItem(
        evidence_id="E1",
        source="dom",
        type="cancel_action_visually_deemphasized",
        description="Cancel button deemphasized",
        element_ref="BTN_CANCEL_1",
    )
    item2 = EvidenceItem(
        evidence_id="E2",
        source="dom",
        type="cancel_action_visually_deemphasized",
        description="Cancel button deemphasized duplicate",
        element_ref="BTN_CANCEL_1",
    )
    req = EvidenceFusionRequest(dom_evidence=[item1, item2])
    res = fusion_engine.fuse(req)

    dom_items = [e for e in res.evidence if e.source == "dom"]
    assert len(dom_items) == 1
    assert dom_items[0].element_ref == "BTN_CANCEL_1"


def test_adapter_behavior_dict_input():
    """Validate adapt_behavior_evidence directly adapting B3 dict output."""
    raw_b3 = {
        "behavior_signals": [
            {
                "type": "retention_friction",
                "detected": True,
                "strength": "moderate",
                "reason": "Retention offer interrupted cancel flow",
                "event_indices": [3, 4],
                "route_sequence": ["/account", "/cancel"],
            }
        ]
    }
    adapted = adapt_behavior_evidence(raw_b3)
    assert len(adapted) == 1
    assert adapted[0].source == "behavior"
    assert adapted[0].type == "retention_friction"
    assert adapted[0].strength == "moderate"
    assert adapted[0].event_indices == [3, 4]
    assert adapted[0].route == "/cancel"
    assert adapted[0].model_confidence is None


def test_adapter_dom_dict_input():
    """Validate adapt_dom_evidence directly adapting B4 dict output."""
    raw_b4 = {
        "dom_signals": [
            {
                "type": "cancel_action_visually_deemphasized",
                "detected": True,
                "strength": "strong",
                "reason": "Cancel option styled with 1.2:1 contrast ratio",
                "element_ref": "BTN_CANCEL",
                "event_indices": [2],
                "route": "/cancel",
                "dom_properties": {"contrast_ratio": 1.2},
            }
        ]
    }
    adapted = adapt_dom_evidence(raw_b4)
    assert len(adapted) == 1
    assert adapted[0].source == "dom"
    assert adapted[0].type == "cancel_action_visually_deemphasized"
    assert adapted[0].element_ref == "BTN_CANCEL"
    assert adapted[0].metadata["dom_properties"]["contrast_ratio"] == 1.2
    assert adapted[0].model_confidence is None
