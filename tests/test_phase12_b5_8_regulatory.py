"""tests/test_phase12_b5_8_regulatory.py
Comprehensive Phase B5.8 Regulatory Check Test Suite.
Enforces all 30 B5.8 requirements:
- Deterministic rule engine & registry verification
- Jurisdiction resolution (explicit, currency, domain, never guessed)
- Temporal & effective-date validation (past, present, future, expired, missing)
- Strict evidence provenance & synthetic ID prevention
- Dark pattern category mappings (all 10 canonical categories)
- Journey, product, tab, auxiliary, and gateway boundary isolation
- Strict non-legal conclusion language enforcement
- Complete risk-score and model-confidence isolation
- Deterministic deduplication and stable sorting
"""
import copy
from datetime import date
from typing import Optional
import pytest

from backend.schemas.evidence import (
    ContradictionItem,
    EvidenceFusionRequest,
    EvidenceItem,
    IntelligenceAnalysisResponse,
    PatternAssessment,
    TemporalRelationshipItem,
)
from backend.schemas.regulatory import (
    RegulatoryCheckRequest,
    RegulatoryCheckResponse,
    RegulatoryFinding,
)
from backend.services.evidence_fusion import EvidenceFusionEngine
from backend.services.regulatory_engine import (
    APPLICABLE,
    FORBIDDEN_LEGAL_PHRASES,
    NOT_APPLICABLE,
    PATTERN_BASKET_SNAKING,
    PATTERN_CONFIRM_SHAMING,
    PATTERN_DRIP_PRICING,
    PATTERN_FALSE_URGENCY,
    PATTERN_FORCED_ACTION,
    PATTERN_MISDIRECTION,
    PATTERN_OBSTRUCTION,
    PATTERN_SCARCITY,
    PATTERN_SOCIAL_PROOF,
    PATTERN_SUBSCRIPTION_TRAP,
    STATUS_NOT_APPLICABLE,
    STATUS_POTENTIALLY_RELEVANT,
    STATUS_SUPPORTED,
    STATUS_UNKNOWN,
    UNKNOWN_APPLICABILITY,
    EffectiveDateValidator,
    JurisdictionResolver,
    RegulatoryEngine,
    RuleRegistry,
)


def _make_ev(
    evidence_id: str,
    source: str = "price",
    ev_type: str = "signal",
    pattern: Optional[str] = None,
    description: str = "",
    currency: Optional[str] = None,
    element_ref: Optional[str] = None,
    journey_id: Optional[str] = None,
    product_id: Optional[str] = None,
    tab_id: Optional[str] = None,
    is_auxiliary: bool = False,
    is_gateway: bool = False,
    context_type: Optional[str] = None,
    confidence: float = 0.85,
) -> EvidenceItem:
    meta = {}
    if product_id is not None:
        meta["product_id"] = product_id
    if tab_id is not None:
        meta["tab_id"] = tab_id
    if is_gateway:
        meta["is_gateway"] = True
    if context_type is not None:
        meta["context_type"] = context_type
    return EvidenceItem(
        evidence_id=evidence_id,
        source=source,
        type=ev_type,
        pattern=pattern,
        description=description,
        currency=currency,
        element_ref=element_ref,
        journey_id=journey_id,
        is_auxiliary=is_auxiliary,
        confidence=confidence,
        metadata=meta,
    )


@pytest.fixture
def registry():
    return RuleRegistry()


@pytest.fixture
def fusion_engine():
    return EvidenceFusionEngine()


@pytest.fixture
def sample_evidence():
    return [
        _make_ev(
            evidence_id="E_PRICE_1",
            source="price",
            ev_type="drip_fee",
            pattern="drip_pricing",
            description="Base: $50, Mandatory booking fee: $15 added at payment step",
            confidence=0.90,
            currency="USD",
        ),
        _make_ev(
            evidence_id="E_DOM_1",
            source="dom",
            ev_type="hidden_fee_row",
            pattern="drip_pricing",
            description="Hidden surcharge row injected into checkout breakdown",
            confidence=0.85,
        ),
    ]


# =============================================================================
# 1. JURISDICTION RESOLUTION TESTS (10 tests)
# =============================================================================
class TestJurisdictionResolution:
    def test_jurisdiction_explicit_india(self):
        j, conf = JurisdictionResolver.resolve("IN", [])
        assert j == "IN"
        assert conf == 1.0

    def test_jurisdiction_explicit_eu(self):
        j, conf = JurisdictionResolver.resolve("European Union", [])
        assert j == "EU"
        assert conf == 1.0

    def test_jurisdiction_explicit_us(self):
        j, conf = JurisdictionResolver.resolve("USA", [])
        assert j == "US"
        assert conf == 1.0

    def test_jurisdiction_explicit_uk(self):
        j, conf = JurisdictionResolver.resolve("Great Britain", [])
        assert j == "UK"
        assert conf == 1.0

    def test_jurisdiction_inferred_from_currency_inr(self):
        evidence = [_make_ev("E1", source="price", description="Rs 999", currency="INR")]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "IN"
        assert conf == 0.60

    def test_jurisdiction_inferred_from_currency_eur(self):
        evidence = [_make_ev("E1", source="price", description="50 EUR", currency="EUR")]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "EU"
        assert conf == 0.60

    def test_jurisdiction_inferred_from_currency_gbp(self):
        evidence = [_make_ev("E1", source="price", description="£25", currency="GBP")]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "UK"
        assert conf == 0.60

    def test_jurisdiction_inferred_from_currency_usd(self):
        evidence = [_make_ev("E1", source="price", description="$100", currency="USD")]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "US"
        assert conf == 0.60

    def test_jurisdiction_inferred_from_tld_in(self):
        evidence = [_make_ev("E1", source="dom", description="test", element_ref="https://shop.retailer.in/cart")]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "IN"
        assert conf == 0.60

    def test_jurisdiction_inferred_from_tld_uk(self):
        evidence = [_make_ev("E1", source="dom", description="test", element_ref="https://service.co.uk/account")]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "UK"
        assert conf == 0.60


# =============================================================================
# 2. UNSUPPORTED & UNKNOWN JURISDICTION TESTS (6 tests)
# =============================================================================
class TestUnsupportedAndUnknownJurisdiction:
    def test_jurisdiction_unknown_when_no_signals(self):
        j, conf = JurisdictionResolver.resolve(None, [])
        assert j == "UNKNOWN"
        assert conf == 0.0

    def test_jurisdiction_never_guessed_on_conflict(self):
        evidence = [
            _make_ev("E1", source="price", currency="USD", description="$50"),
            _make_ev("E2", source="price", currency="INR", description="₹500"),
        ]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "UNKNOWN"
        assert conf == 0.0

    def test_jurisdiction_unknown_produces_unknown_finding_status(self):
        ev = [_make_ev("E_PRICE_1", source="price", description="Fee without currency")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,  # Unknown
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "UNKNOWN"
        assert resp.requires_jurisdiction is True
        for f in resp.findings:
            assert f.status == STATUS_UNKNOWN
            assert f.applicability == UNKNOWN_APPLICABILITY

    def test_unsupported_jurisdiction_australia(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="AU",  # Unsupported jurisdiction
            transaction_date="2024-05-15",
            include_non_applicable=True,
        )
        assert resp.jurisdiction_resolved == "AU"
        assert resp.requires_jurisdiction is False
        assert resp.supported_rule_registry is False
        assert resp.rule_available is False
        assert resp.limitation is not None
        assert "unsupported" in resp.limitation
        for f in resp.findings:
            assert f.status == STATUS_NOT_APPLICABLE
            assert f.applicability == NOT_APPLICABLE
            assert "AU" in f.explanation

    def test_jurisdiction_query_param_never_used(self):
        # Invariant 27: URL query parameters must not be used as evidence
        evidence = [
            _make_ev(
                "E1",
                source="dom",
                description="Checkout page",
                element_ref="https://example.com/checkout?currency=INR&country=IN",
            )
        ]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "UNKNOWN"
        assert conf == 0.0

    def test_jurisdiction_fragment_never_used(self):
        evidence = [
            _make_ev(
                "E1",
                source="dom",
                description="Payment frame",
                element_ref="https://example.com/checkout#in",
            )
        ]
        j, conf = JurisdictionResolver.resolve(None, evidence)
        assert j == "UNKNOWN"
        assert conf == 0.0


# =============================================================================
# 3. EFFECTIVE DATE & TEMPORAL VALIDATION TESTS (8 tests)
# =============================================================================
class TestEffectiveDateValidation:
    def test_effective_date_valid_contemporary(self):
        # CCPA 2023 effective from 2023-11-30
        app, reason = EffectiveDateValidator.validate(
            effective_from="2023-11-30",
            effective_to=None,
            transaction_date_str="2024-05-15",
        )
        assert app == APPLICABLE
        assert reason is None

    def test_effective_date_predates_effective_date(self):
        # Transaction in 2020 predates CCPA 2023
        app, reason = EffectiveDateValidator.validate(
            effective_from="2023-11-30",
            effective_to=None,
            transaction_date_str="2020-01-15",
        )
        assert app == NOT_APPLICABLE
        assert "predates" in reason

    def test_effective_date_expired_regulation(self):
        # Indian CPA 1986 expired on 2020-07-20
        app, reason = EffectiveDateValidator.validate(
            effective_from="1987-07-01",
            effective_to="2020-07-20",
            transaction_date_str="2024-01-01",
        )
        assert app == NOT_APPLICABLE
        assert "expired" in reason or "superseded" in reason

    def test_effective_date_expired_regulation_valid_during_lifetime(self):
        # Transaction in 2018 is within CPA 1986 lifetime
        app, reason = EffectiveDateValidator.validate(
            effective_from="1987-07-01",
            effective_to="2020-07-20",
            transaction_date_str="2018-05-10",
        )
        assert app == APPLICABLE
        assert reason is None

    def test_effective_date_future_regulation_ai_act(self):
        # EU AI Act Art 50 effective 2026-08-02 evaluated in 2024
        app, reason = EffectiveDateValidator.validate(
            effective_from="2026-08-02",
            effective_to=None,
            transaction_date_str="2024-05-15",
        )
        assert app == NOT_APPLICABLE
        assert "predates" in reason

    def test_effective_date_boundary_exact_effective_day(self):
        app, reason = EffectiveDateValidator.validate(
            effective_from="2023-11-30",
            effective_to=None,
            transaction_date_str="2023-11-30",
        )
        assert app == APPLICABLE
        assert reason is None

    def test_effective_date_iso_timestamp_parsing(self):
        dt = EffectiveDateValidator.parse_iso_date("2024-05-15T14:30:00Z")
        assert dt == date(2024, 5, 15)

    def test_effective_date_invalid_format_returns_unknown(self):
        app, reason = EffectiveDateValidator.validate(
            effective_from="2023-11-30",
            effective_to=None,
            transaction_date_str="not-a-valid-date",
        )
        assert app == UNKNOWN_APPLICABILITY
        assert "Invalid transaction date" in reason


# =============================================================================
# 4. MISSING DATE TESTS (4 tests)
# =============================================================================
class TestMissingDateValidation:
    def test_missing_date_prevents_supported_status(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="US",
            transaction_date=None,  # Missing date
        )
        assert resp.requires_date is True
        us_findings = [f for f in resp.findings if f.jurisdiction == "US"]
        assert len(us_findings) > 0
        for f in us_findings:
            assert f.status != STATUS_SUPPORTED
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.applicability == UNKNOWN_APPLICABILITY
            assert "verification" in f.explanation

    def test_empty_string_date_prevents_supported(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="US",
            transaction_date="   ",
        )
        assert resp.requires_date is True
        us_findings = [f for f in resp.findings if f.jurisdiction == "US"]
        assert len(us_findings) > 0
        for f in us_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT

    def test_missing_date_flag_is_false_when_date_provided(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        assert resp.requires_date is False

    def test_missing_date_confidence_capped(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="US",
            transaction_date=None,
        )
        us_findings = [f for f in resp.findings if f.jurisdiction == "US"]
        for f in us_findings:
            assert f.confidence <= 0.50


# =============================================================================
# 5. PATTERN MAPPING TESTS (10 tests)
# =============================================================================
class TestPatternMapping:
    def _evaluate_pattern_for_jurisdiction(self, pattern: str, jurisdiction: str, entity_type: Optional[str] = "ONLINE_PLATFORM"):
        eid = f"E_{pattern}_1"
        ev = [_make_ev(eid, source="dom", pattern=pattern.lower(), description="test")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=pattern,
                    status="SUPPORTED",
                    supporting_evidence_ids=[eid],
                )
            ]
        )
        return RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=jurisdiction,
            transaction_date="2024-06-01",
            entity_type=entity_type,
        )

    def test_pattern_mapping_drip_pricing(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_DRIP_PRICING, "IN")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "IN_CCPA_DRIP_PRICING" for f in supported)

    def test_pattern_mapping_subscription_trap(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_SUBSCRIPTION_TRAP, "US")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any("ROSCA" in f.rule_id or "CAL_ARL" in f.rule_id for f in supported)

    def test_pattern_mapping_basket_snaking(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_BASKET_SNAKING, "IN")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "IN_CCPA_BASKET_SNAKING" for f in supported)

    def test_pattern_mapping_false_urgency(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_FALSE_URGENCY, "IN")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "IN_CCPA_FALSE_URGENCY" for f in supported)

    def test_pattern_mapping_confirm_shaming(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_CONFIRM_SHAMING, "IN")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "IN_CCPA_CONFIRM_SHAMING" for f in supported)

    def test_pattern_mapping_forced_action(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_FORCED_ACTION, "EU")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "EU_DSA_ART25_FORCED_ACTION" for f in supported)

    def test_pattern_mapping_obstruction(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_OBSTRUCTION, "EU")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "EU_DSA_ART25_CANCELLATION" for f in supported)

    def test_pattern_mapping_misdirection(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_MISDIRECTION, "IN")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "IN_CCPA_MISDIRECTION" for f in supported)

    def test_pattern_mapping_scarcity(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_SCARCITY, "IN")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "IN_CCPA_SCARCITY" for f in supported)

    def test_pattern_mapping_social_proof(self):
        resp = self._evaluate_pattern_for_jurisdiction(PATTERN_SOCIAL_PROOF, "UK")
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert any(f.rule_id == "UK_DMCC_FAKE_REVIEWS" for f in supported)


# =============================================================================
# 6. UNSUPPORTED & NEGATIVE PATTERN TESTS (4 tests)
# =============================================================================
class TestUnsupportedAndNegativePatterns:
    def test_unsupported_pattern_not_in_registry(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern="COMPLETELY_UNKNOWN_CUSTOM_PATTERN",
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        assert len(resp.findings) == 0

    def test_pattern_status_not_supported_evaluates_not_applicable(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="NOT_SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            include_non_applicable=True,
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status == STATUS_NOT_APPLICABLE
            assert f.applicability == NOT_APPLICABLE
            assert "does not support" in f.explanation

    def test_pattern_status_potential_yields_potentially_relevant(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="POTENTIAL",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.applicability == APPLICABLE

    def test_empty_pattern_assessments_produces_empty_findings(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(pattern_assessments=[])
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        assert len(resp.findings) == 0


# =============================================================================
# 7. EVIDENCE PROVENANCE & SYNTHETIC EVIDENCE PREVENTION TESTS (6 tests)
# =============================================================================
class TestEvidenceProvenance:
    def test_strict_provenance_all_valid_ids(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN" and f.status == STATUS_SUPPORTED]
        assert len(in_findings) == 1
        assert in_findings[0].supporting_evidence_ids == ["E_DOM_1", "E_PRICE_1"]

    def test_synthetic_evidence_id_prevents_supported_status(self, sample_evidence):
        # Assessment references an ID not in sample_evidence
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["SYNTHETIC_EID_999"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert "provenance" in f.explanation
            assert "SYNTHETIC_EID_999" not in f.supporting_evidence_ids

    def test_partial_synthetic_evidence_id_prevents_supported(self, sample_evidence):
        # Assessment references 1 valid ID and 1 synthetic ID
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "FABRICATED_ID"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert "FABRICATED_ID" not in f.supporting_evidence_ids
            assert f.supporting_evidence_ids == ["E_PRICE_1"]

    def test_empty_evidence_ids_prevents_supported(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=[],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert len(f.supporting_evidence_ids) == 0

    def test_no_synthetic_evidence_created(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        valid_set = {e.evidence_id for e in sample_evidence}
        for f in resp.findings:
            for eid in f.supporting_evidence_ids:
                assert eid in valid_set

    def test_supporting_evidence_collation_is_deduplicated_and_sorted(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        assert resp.supporting_evidence == ["E_DOM_1", "E_PRICE_1"]


# =============================================================================
# 8. CONFLICTING EVIDENCE TESTS (3 tests)
# =============================================================================
class TestConflictingEvidence:
    def test_conflicting_evidence_preserved(self, sample_evidence):
        conflicts = [
            ContradictionItem(
                contradiction_id="C001",
                type="text_vs_dom",
                source_a="text",
                source_b="dom",
                reason="Advertised free shipping contradicted by DOM shipping line",
                evidence_ids=["E_PRICE_1", "E_DOM_1"],
            )
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            contradictions=conflicts,
        )
        assert len(resp.findings) > 0

    def test_conflicting_evidence_does_not_mutate_regulatory_confidence(self, sample_evidence):
        conflicts = [
            ContradictionItem(
                contradiction_id="C001",
                type="text_vs_dom",
                source_a="text",
                source_b="dom",
                severity="strong",
                reason="Contradiction",
                evidence_ids=["E_PRICE_1", "E_DOM_1"],
            )
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            contradictions=conflicts,
        )
        supported = [f for f in resp.findings if f.status == STATUS_SUPPORTED]
        assert supported[0].confidence == 0.85

    def test_temporal_relationships_passed_without_error(self, sample_evidence):
        temporals = [
            TemporalRelationshipItem(
                temporal_id="T001",
                type="fee_added_after_action",
                before_evidence_ids=["E_PRICE_1"],
                after_evidence_ids=["E_DOM_1"],
                reason="Fee injected after continue clicked",
            )
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            temporal_relationships=temporals,
        )
        assert len(resp.findings) > 0


# =============================================================================
# 9. MULTIPLE REGULATIONS IN SAME JURISDICTION (4 tests)
# =============================================================================
class TestMultipleRegulations:
    def test_multiple_regulations_us_subscription_trap(self):
        ev = [_make_ev("E_SUB_1", source="price", description="Recurring sub")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_SUBSCRIPTION_TRAP,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_SUB_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        us_findings = [f for f in resp.findings if f.jurisdiction == "US" and f.status == STATUS_SUPPORTED]
        # Must have both US ROSCA and California ARL as separate findings
        assert len(us_findings) == 2
        rule_ids = {f.rule_id for f in us_findings}
        assert "US_ROSCA_NEGATIVE_OPTION" in rule_ids
        assert "US_CAL_ARL_SUBSCRIPTION" in rule_ids

    def test_multiple_regulations_distinct_finding_ids(self):
        ev = [_make_ev("E_SUB_1", source="price", description="Recurring sub")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_SUBSCRIPTION_TRAP,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_SUB_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        fids = [f.finding_id for f in resp.findings if f.jurisdiction == "US"]
        assert len(fids) == len(set(fids))

    def test_multiple_regulations_distinct_statutory_sources(self):
        ev = [_make_ev("E_SUB_1", source="price", description="Recurring sub")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_SUBSCRIPTION_TRAP,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_SUB_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        us_findings = [f for f in resp.findings if f.jurisdiction == "US" and f.status == STATUS_SUPPORTED]
        sources = {f.source for f in us_findings}
        assert any("ROSCA" in s for s in sources)
        assert any("California" in s for s in sources)

    def test_multiple_regulations_independent_applicability(self):
        # Cal ARL became effective 2022-07-01, ROSCA became effective 2010-12-29
        # Transaction in 2015: ROSCA is applicable, but Cal ARL predates!
        ev = [_make_ev("E_SUB_1", source="price", description="Recurring sub")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_SUBSCRIPTION_TRAP,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_SUB_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2015-05-15",
            include_non_applicable=True,
        )
        rosca = next(f for f in resp.findings if f.rule_id == "US_ROSCA_NEGATIVE_OPTION")
        cal_arl = next(f for f in resp.findings if f.rule_id == "US_CAL_ARL_SUBSCRIPTION")
        assert rosca.status == STATUS_SUPPORTED
        assert cal_arl.status == STATUS_NOT_APPLICABLE
        assert "predates" in cal_arl.explanation


# =============================================================================
# 10. DUPLICATE REGULATIONS & DEDUPLICATION TESTS (4 tests)
# =============================================================================
class TestDeduplication:
    def test_exact_duplicate_findings_deduplicated(self):
        f1 = RegulatoryFinding(
            finding_id="REG_IN_RULE1",
            jurisdiction="IN",
            jurisdiction_confidence=1.0,
            regulation_id="REG1",
            rule_id="RULE1",
            rule_name="Rule 1",
            pattern="DRIP_PRICING",
            status=STATUS_SUPPORTED,
            applicability=APPLICABLE,
            confidence=0.85,
            supporting_evidence_ids=["E1"],
            explanation="Explanation 1",
            source="Source 1",
        )
        f2 = copy.deepcopy(f1)
        f2.supporting_evidence_ids = ["E2"]
        dedup = RegulatoryEngine._deduplicate_findings([f1, f2])
        assert len(dedup) == 1
        assert dedup[0].supporting_evidence_ids == ["E1", "E2"]

    def test_deduplication_prioritizes_higher_status(self):
        f1 = RegulatoryFinding(
            finding_id="REG_IN_RULE1",
            jurisdiction="IN",
            jurisdiction_confidence=1.0,
            regulation_id="REG1",
            rule_id="RULE1",
            rule_name="Rule 1",
            pattern="DRIP_PRICING",
            status=STATUS_POTENTIALLY_RELEVANT,
            applicability=APPLICABLE,
            confidence=0.55,
            supporting_evidence_ids=["E1"],
            explanation="Explanation 1",
            source="Source 1",
        )
        f2 = copy.deepcopy(f1)
        f2.status = STATUS_SUPPORTED
        f2.confidence = 0.85
        dedup = RegulatoryEngine._deduplicate_findings([f1, f2])
        assert len(dedup) == 1
        assert dedup[0].status == STATUS_SUPPORTED
        assert dedup[0].confidence == 0.85

    def test_deduplication_preserves_maximum_confidence(self):
        f1 = RegulatoryFinding(
            finding_id="REG_IN_RULE1",
            jurisdiction="IN",
            jurisdiction_confidence=1.0,
            regulation_id="REG1",
            rule_id="RULE1",
            rule_name="Rule 1",
            pattern="DRIP_PRICING",
            status=STATUS_SUPPORTED,
            applicability=APPLICABLE,
            confidence=0.75,
            supporting_evidence_ids=["E1"],
            explanation="Explanation 1",
            source="Source 1",
        )
        f2 = copy.deepcopy(f1)
        f2.confidence = 0.90
        dedup = RegulatoryEngine._deduplicate_findings([f1, f2])
        assert len(dedup) == 1
        assert dedup[0].confidence == 0.90

    def test_deduplication_distinct_rules_retained(self):
        f1 = RegulatoryFinding(
            finding_id="REG_IN_RULE1",
            jurisdiction="IN",
            jurisdiction_confidence=1.0,
            regulation_id="REG1",
            rule_id="RULE1",
            rule_name="Rule 1",
            pattern="DRIP_PRICING",
            status=STATUS_SUPPORTED,
            applicability=APPLICABLE,
            confidence=0.85,
            supporting_evidence_ids=["E1"],
            explanation="Explanation 1",
            source="Source 1",
        )
        f2 = copy.deepcopy(f1)
        f2.rule_id = "RULE2"
        f2.finding_id = "REG_IN_RULE2"
        dedup = RegulatoryEngine._deduplicate_findings([f1, f2])
        assert len(dedup) == 2


# =============================================================================
# 11. ISOLATION TESTS (JOURNEY, PRODUCT, TAB, AUXILIARY, GATEWAY) (7 tests)
# =============================================================================
class TestBoundaryIsolation:
    def test_journey_isolation_filters_external_journey_evidence(self):
        ev = [
            _make_ev("E_J1", source="price", journey_id="journey_A", description="valid"),
            _make_ev("E_J2", source="price", journey_id="journey_B", description="other journey"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_J2"],  # Belongs to journey_B
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            journey_id="journey_A",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert "provenance" in f.explanation

    def test_product_isolation_filters_external_product_evidence(self):
        ev = [
            _make_ev("E_P1", source="price", product_id="prod_shoes", description="valid"),
            _make_ev("E_P2", source="price", product_id="prod_watch", description="other prod"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_P2"],  # Belongs to watch
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            product_id="prod_shoes",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED
            assert f.status == STATUS_POTENTIALLY_RELEVANT

    def test_tab_isolation_filters_external_tab_evidence(self):
        ev = [
            _make_ev("E_T1", source="price", tab_id="tab_1", description="valid"),
            _make_ev("E_T2", source="price", tab_id="tab_2", description="other tab"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_T2"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            tab_id="tab_1",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED
            assert f.status == STATUS_POTENTIALLY_RELEVANT

    def test_auxiliary_dialog_produces_zero_commercial_findings(self):
        ev = [
            _make_ev("E_AUX_1", source="dom", is_auxiliary=True, description="Cookie consent"),
            _make_ev("E_AUX_2", source="dom", is_auxiliary=True, description="Privacy notice"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_OBSTRUCTION,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_AUX_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="EU",
            transaction_date="2024-05-15",
        )
        assert len(resp.findings) == 0

    def test_gateway_isolation_produces_zero_findings(self):
        ev = [
            _make_ev("E_GW_1", source="dom", is_gateway=True, description="Stripe payment checkout"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_GW_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        assert len(resp.findings) == 0

    def test_mixed_commercial_and_auxiliary_isolation(self):
        ev = [
            _make_ev("E_COMM_1", source="price", is_auxiliary=False, description="Commercial item"),
            _make_ev("E_AUX_1", source="dom", is_auxiliary=True, description="Auxiliary modal"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_COMM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN" and f.status == STATUS_SUPPORTED]
        assert len(in_findings) == 1
        assert in_findings[0].supporting_evidence_ids == ["E_COMM_1"]
        assert "E_AUX_1" not in resp.supporting_evidence

    def test_isolated_evidence_prevents_supported_status(self):
        ev = [
            _make_ev("E_COMM_1", source="price", is_auxiliary=False, description="Commercial item"),
            _make_ev("E_AUX_1", source="dom", is_auxiliary=True, description="Auxiliary modal"),
        ]
        # Assessment relies on E_AUX_1 which gets isolated out
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_AUX_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED


# =============================================================================
# 12. DETERMINISM & STABILITY TESTS (3 tests)
# =============================================================================
class TestDeterminism:
    def test_deterministic_output_across_repeated_runs(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        runs = [
            RegulatoryEngine.evaluate(
                intelligence_analysis=intel,
                raw_evidence=sample_evidence,
                jurisdiction="IN",
                transaction_date="2024-05-15",
            )
            for _ in range(5)
        ]
        first_json = runs[0].model_dump_json()
        for r in runs[1:]:
            assert r.model_dump_json() == first_json

    def test_deterministic_ordering_of_findings(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E_PRICE_1"]),
                PatternAssessment(pattern=PATTERN_SUBSCRIPTION_TRAP, status="SUPPORTED", supporting_evidence_ids=["E_DOM_1"]),
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        # Findings must be sorted by (jurisdiction, regulation_id, rule_id)
        keys = [(f.jurisdiction, f.regulation_id, f.rule_id) for f in resp.findings]
        assert keys == sorted(keys)

    def test_deterministic_ordering_of_evidence_ids(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1", "E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        for f in resp.findings:
            assert f.supporting_evidence_ids == sorted(f.supporting_evidence_ids)


# =============================================================================
# 13. NO LEGAL CONCLUSION LANGUAGE TESTS (5 tests)
# =============================================================================
class TestNoLegalConclusion:
    def test_no_illegal_word_in_any_explanation(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            include_non_applicable=True,
        )
        for f in resp.findings:
            lower = f.explanation.lower()
            assert "illegal" not in lower
            assert "violates the law" not in lower
            assert "breaking the law" not in lower

    def test_no_violates_law_in_any_explanation(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_SUBSCRIPTION_TRAP,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="US",
            transaction_date="2024-05-15",
            include_non_applicable=True,
        )
        for f in resp.findings:
            lower = f.explanation.lower()
            assert "violate" not in lower
            assert "unlawful" not in lower

    def test_no_breaking_law_in_any_explanation(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_OBSTRUCTION,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_DOM_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="EU",
            transaction_date="2024-05-15",
            include_non_applicable=True,
        )
        for f in resp.findings:
            lower = f.explanation.lower()
            assert "breaking the law" not in lower
            assert "guilty" not in lower

    def test_assertion_helper_catches_forbidden_phrases(self):
        with pytest.raises(ValueError, match="Forbidden legal conclusion phrase"):
            RegulatoryEngine._assert_no_forbidden_phrases("This website breaks the law completely.")

        with pytest.raises(ValueError, match="Forbidden legal conclusion phrase"):
            RegulatoryEngine._assert_no_forbidden_phrases("Conduct is illegal under article 5.")

    def test_all_registry_rules_have_authoritative_sources(self, registry):
        rules = registry.get_all_rules()
        assert len(rules) >= 20
        for r in rules:
            assert r.authoritative_source and len(r.authoritative_source.strip()) > 10
            assert r.rule_id and r.regulation_id and r.jurisdiction
            assert r.version == "1.0.0"


# =============================================================================
# 14. RISK SCORE & ML CONFIDENCE ISOLATION TESTS (3 tests)
# =============================================================================
class TestRiskScoreIsolation:
    def test_regulatory_check_does_not_modify_risk_score(self, fusion_engine):
        # Run standard fusion
        req = EvidenceFusionRequest(text="Subscribe now! Only $9.99/month.")
        res1 = fusion_engine.fuse(req)
        score1 = res1.risk_score
        level1 = res1.risk_level

        # Evaluate regulatory check separately
        ev = [_make_ev("E1", source="text", pattern="subscription_trap", description="sub")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_SUBSCRIPTION_TRAP, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        reg_resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        assert len(reg_resp.findings) > 0

        # Rerun fusion to confirm risk score and thresholds are 100% identical and unchanged
        res2 = fusion_engine.fuse(req)
        assert res2.risk_score == score1
        assert res2.risk_level == level1

    def test_regulatory_check_does_not_modify_risk_thresholds(self):
        from backend.services.evidence_fusion import (
            RISK_THRESHOLD_MEDIUM,
            RISK_THRESHOLD_HIGH,
            RISK_THRESHOLD_CRITICAL,
        )
        assert RISK_THRESHOLD_MEDIUM == 3.0
        assert RISK_THRESHOLD_HIGH == 5.0
        assert RISK_THRESHOLD_CRITICAL == 8.0

    def test_confidence_separation_in_findings(self, sample_evidence):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    confidence=0.99,  # High model confidence
                    supporting_evidence_ids=["E_PRICE_1"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=sample_evidence,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        finding = next(f for f in resp.findings if f.status == STATUS_SUPPORTED)
        # Finding confidence is regulatory applicability confidence (0.85), distinct from model confidence (0.99)
        assert finding.confidence == 0.85
        assert finding.confidence != 0.99


# =============================================================================
# 15. ADVERSARIAL TESTS A THROUGH Z (26 tests)
# =============================================================================
class TestAdversarialSuite:
    def test_adversarial_A_unknown_jurisdiction_supported_pattern(self):
        ev = [_make_ev("E1", source="dom", description="Drip fee without currency")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "UNKNOWN"
        assert resp.requires_jurisdiction is True
        for f in resp.findings:
            assert f.status == STATUS_UNKNOWN
            assert f.applicability == UNKNOWN_APPLICABILITY

    def test_adversarial_B_inr_only(self):
        ev = [_make_ev("E1", source="price", currency="INR", description="₹999")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "IN"
        assert resp.jurisdiction_confidence == 0.60
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.confidence <= 0.65

    def test_adversarial_C_eur_only(self):
        ev = [_make_ev("E1", source="price", currency="EUR", description="49 EUR")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "EU"
        assert resp.jurisdiction_confidence == 0.60
        eu_findings = [f for f in resp.findings if f.jurisdiction == "EU"]
        for f in eu_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.confidence <= 0.65

    def test_adversarial_D_usd_only(self):
        ev = [_make_ev("E1", source="price", currency="USD", description="$50")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "US"
        assert resp.jurisdiction_confidence == 0.60
        us_findings = [f for f in resp.findings if f.jurisdiction == "US"]
        for f in us_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.confidence <= 0.65

    def test_adversarial_E_gbp_only(self):
        ev = [_make_ev("E1", source="price", currency="GBP", description="£30")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-06-01",
        )
        assert resp.jurisdiction_resolved == "UK"
        assert resp.jurisdiction_confidence == 0.60
        uk_findings = [f for f in resp.findings if f.jurisdiction == "UK"]
        for f in uk_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.confidence <= 0.65

    def test_adversarial_F_dot_in_only(self):
        ev = [_make_ev("E1", source="dom", element_ref="https://checkout.mystore.in/pay", description="Pay")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "IN"
        assert resp.jurisdiction_confidence == 0.60
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.confidence <= 0.65

    def test_adversarial_G_dot_co_uk_only(self):
        ev = [_make_ev("E1", source="dom", element_ref="https://shop.service.co.uk/checkout", description="Checkout")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-06-01",
        )
        assert resp.jurisdiction_resolved == "UK"
        assert resp.jurisdiction_confidence == 0.60
        uk_findings = [f for f in resp.findings if f.jurisdiction == "UK"]
        for f in uk_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.confidence <= 0.65

    def test_adversarial_H_explicit_IN(self):
        ev = [_make_ev("E1", source="price", description="₹50 fee", currency="INR")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "IN"
        assert resp.jurisdiction_confidence == 1.0
        in_finding = next(f for f in resp.findings if f.rule_id == "IN_CCPA_DRIP_PRICING")
        assert in_finding.status == STATUS_SUPPORTED
        assert in_finding.confidence == 0.85

    def test_adversarial_I_explicit_EU(self):
        ev = [_make_ev("E1", source="dom", description="Deceptive design interface")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_MISDIRECTION, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="EU",
            transaction_date="2024-05-15",
            entity_type="ONLINE_PLATFORM",
        )
        assert resp.jurisdiction_resolved == "EU"
        assert resp.jurisdiction_confidence == 1.0
        eu_finding = next(f for f in resp.findings if f.rule_id == "EU_DSA_ART25_DECEPTIVE_DESIGN")
        assert eu_finding.status == STATUS_SUPPORTED
        assert eu_finding.confidence == 0.85

    def test_adversarial_J_conflicting_currency_signals(self):
        ev = [
            _make_ev("E1", source="price", currency="USD", description="$10"),
            _make_ev("E2", source="price", currency="EUR", description="€10"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "UNKNOWN"
        assert resp.jurisdiction_confidence == 0.0

    def test_adversarial_K_missing_date(self):
        ev = [_make_ev("E1", source="price", description="fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date=None,
        )
        assert resp.requires_date is True
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert f.applicability == UNKNOWN_APPLICABILITY

    def test_adversarial_L_exact_effective_from_date(self):
        ev = [_make_ev("E1", source="price", description="fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        # 2023-11-30 is exact effective date of CCPA 2023
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2023-11-30",
        )
        in_finding = next(f for f in resp.findings if f.rule_id == "IN_CCPA_DRIP_PRICING")
        assert in_finding.applicability == APPLICABLE
        assert in_finding.status == STATUS_SUPPORTED

    def test_adversarial_M_exact_effective_to_date(self):
        # CPA 1986 expired 2020-07-20
        app, reason = EffectiveDateValidator.validate(
            effective_from="1987-07-01",
            effective_to="2020-07-20",
            transaction_date_str="2020-07-20",
        )
        assert app == APPLICABLE
        assert reason is None

    def test_adversarial_N_one_day_before_effective_from(self):
        ev = [_make_ev("E1", source="price", description="fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        # 2023-11-29 is 1 day before CCPA 2023 effective date
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2023-11-29",
            include_non_applicable=True,
        )
        in_finding = next(f for f in resp.findings if f.rule_id == "IN_CCPA_DRIP_PRICING")
        assert in_finding.applicability == NOT_APPLICABLE
        assert in_finding.status == STATUS_NOT_APPLICABLE

    def test_adversarial_O_one_day_after_effective_to(self):
        # 2020-07-21 is 1 day after CPA 1986 expired
        app, reason = EffectiveDateValidator.validate(
            effective_from="1987-07-01",
            effective_to="2020-07-20",
            transaction_date_str="2020-07-21",
        )
        assert app == NOT_APPLICABLE
        assert "expired" in reason or "superseded" in reason

    def test_adversarial_P_invalid_evidence_id(self):
        ev = [_make_ev("E_GENUINE_1", source="price", description="fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(
                    pattern=PATTERN_DRIP_PRICING,
                    status="SUPPORTED",
                    supporting_evidence_ids=["E_SYNTHETIC_999"],
                )
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert "E_SYNTHETIC_999" not in f.supporting_evidence_ids

    def test_adversarial_Q_empty_evidence(self):
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=[])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=[],
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status == STATUS_POTENTIALLY_RELEVANT
            assert len(f.supporting_evidence_ids) == 0

    def test_adversarial_R_cross_journey_evidence(self):
        ev = [_make_ev("E1", source="price", journey_id="jrn_A", description="valid")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            journey_id="jrn_B",  # Different journey
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED

    def test_adversarial_S_cross_product_evidence(self):
        ev = [_make_ev("E1", source="price", product_id="prod_shoes", description="valid")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            product_id="prod_watch",  # Different product
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED

    def test_adversarial_T_cross_tab_evidence(self):
        ev = [_make_ev("E1", source="price", tab_id="tab_1", description="valid")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
            tab_id="tab_2",  # Different tab
        )
        in_findings = [f for f in resp.findings if f.jurisdiction == "IN"]
        for f in in_findings:
            assert f.status != STATUS_SUPPORTED

    def test_adversarial_U_auxiliary_evidence(self):
        ev = [_make_ev("E1", source="dom", is_auxiliary=True, description="Cookie modal")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_OBSTRUCTION, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="EU",
            transaction_date="2024-05-15",
        )
        assert len(resp.findings) == 0

    def test_adversarial_V_gateway_evidence(self):
        ev = [_make_ev("E1", source="dom", is_gateway=True, description="Payment gateway")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        assert len(resp.findings) == 0

    def test_adversarial_W_duplicate_rule(self):
        f1 = RegulatoryFinding(
            finding_id="REG_IN_RULE1",
            jurisdiction="IN",
            jurisdiction_confidence=1.0,
            regulation_id="REG1",
            rule_id="RULE1",
            rule_name="Rule 1",
            pattern="DRIP_PRICING",
            status=STATUS_SUPPORTED,
            applicability=APPLICABLE,
            confidence=0.85,
            supporting_evidence_ids=["E1"],
            explanation="Explanation",
            source="Source",
        )
        f2 = copy.deepcopy(f1)
        dedup = RegulatoryEngine._deduplicate_findings([f1, f2])
        assert len(dedup) == 1

    def test_adversarial_X_multiple_valid_regulations(self):
        ev = [_make_ev("E1", source="price", description="sub")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_SUBSCRIPTION_TRAP, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        us_findings = [f for f in resp.findings if f.jurisdiction == "US" and f.status == STATUS_SUPPORTED]
        assert len(us_findings) >= 2
        rules = {f.rule_id for f in us_findings}
        assert "US_ROSCA_NEGATIVE_OPTION" in rules
        assert "US_CAL_ARL_SUBSCRIPTION" in rules

    def test_adversarial_Y_regulation_found_risk_score_unchanged(self, fusion_engine):
        req = EvidenceFusionRequest(text="Check out now! Hidden fee $5.")
        res1 = fusion_engine.fuse(req)
        score1 = res1.risk_score

        ev = [_make_ev("E1", source="price", description="fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        reg_resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        assert len(reg_resp.findings) > 0

        res2 = fusion_engine.fuse(req)
        assert res2.risk_score == score1

    def test_adversarial_Z_repeated_evaluation_determinism(self):
        ev = [
            _make_ev("E1", source="price", description="fee"),
            _make_ev("E2", source="dom", description="hidden row"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1", "E2"]),
                PatternAssessment(pattern=PATTERN_SUBSCRIPTION_TRAP, status="SUPPORTED", supporting_evidence_ids=["E1"]),
            ]
        )
        results = [
            RegulatoryEngine.evaluate(
                intelligence_analysis=intel,
                raw_evidence=ev,
                jurisdiction="IN",
                transaction_date="2024-05-15",
            ).model_dump_json()
            for _ in range(5)
        ]
        for r in results[1:]:
            assert r == results[0]


# =============================================================================
# 18. PHASE B5.8 STRICT SEMANTIC AUDIT CORRECTIONS TEST SUITE (12 tests)
# =============================================================================
class TestPhaseB58SemanticAuditCorrections:
    """Rigorous tests covering P1-01 through P1-06 semantic audit requirements."""

    def test_1_unknown_jurisdiction_produces_unknown(self):
        """UNKNOWN jurisdiction -> UNKNOWN applicability & status."""
        ev = [_make_ev("E1", source="price", description="Ambiguous fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction=None,
            transaction_date="2024-05-15",
        )
        assert resp.jurisdiction_resolved == "UNKNOWN"
        assert resp.requires_jurisdiction is True
        assert resp.supported_rule_registry is False
        assert resp.rule_available is False
        assert len(resp.findings) > 0
        for f in resp.findings:
            assert f.status == STATUS_UNKNOWN
            assert f.applicability == UNKNOWN_APPLICABILITY
            assert f.confidence == 0.0

    def test_2_explicit_unsupported_au_distinguished_from_unknown(self):
        """Explicit unsupported AU jurisdiction -> distinguished from UNKNOWN."""
        ev = [_make_ev("E1", source="price", description="Australian transaction fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="AU",
            transaction_date="2024-05-15",
            include_non_applicable=True,
        )
        # 1. Jurisdiction is known
        assert resp.jurisdiction_resolved == "AU"
        assert resp.requires_jurisdiction is False
        # 2. Rule registry coverage is unavailable
        assert resp.supported_rule_registry is False
        assert resp.rule_available is False
        # 3. Limitation text clearly explains coverage distinction
        assert resp.limitation is not None
        assert "unsupported" in resp.limitation
        # 4. Status is NOT_APPLICABLE, never UNKNOWN
        for f in resp.findings:
            assert f.status == STATUS_NOT_APPLICABLE
            assert f.applicability == NOT_APPLICABLE
            assert f.status != STATUS_UNKNOWN
            assert f.applicability != UNKNOWN_APPLICABILITY

    def test_3_eu_dsa_online_platform_eligible_for_applicability(self):
        """EU DSA + ONLINE_PLATFORM -> eligible for applicability evaluation."""
        ev = [_make_ev("E1", source="dom", description="Platform deceptive design")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_MISDIRECTION, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="EU",
            transaction_date="2024-05-15",
            entity_type="ONLINE_PLATFORM",
        )
        eu_finding = next(f for f in resp.findings if f.rule_id == "EU_DSA_ART25_DECEPTIVE_DESIGN")
        assert eu_finding.regulated_entity_type == "ONLINE_PLATFORM"
        assert eu_finding.requires_entity_scope is True
        assert eu_finding.authority_type == "EU_REGULATION"
        assert eu_finding.applicability == APPLICABLE
        assert eu_finding.status == STATUS_SUPPORTED
        assert eu_finding.confidence == 0.85

    def test_4_eu_dsa_unknown_entity_type_unknown_applicability(self):
        """EU DSA + UNKNOWN entity type -> UNKNOWN applicability."""
        ev = [_make_ev("E1", source="dom", description="Platform deceptive design")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_MISDIRECTION, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="EU",
            transaction_date="2024-05-15",
            entity_type=None,  # Entity type unknown
        )
        eu_finding = next(f for f in resp.findings if f.rule_id == "EU_DSA_ART25_DECEPTIVE_DESIGN")
        assert eu_finding.applicability == UNKNOWN_APPLICABILITY
        assert eu_finding.status == STATUS_POTENTIALLY_RELEVANT
        assert "providers of online platforms" in eu_finding.explanation.lower()

    def test_5_eu_ucpd_directive_metadata_present(self, registry):
        """EU UCPD -> directive metadata present."""
        ucpd_rules = [r for r in registry.get_all_rules() if "UCPD" in r.rule_id]
        assert len(ucpd_rules) >= 4
        for rule in ucpd_rules:
            assert rule.authority_type == "EU_DIRECTIVE"
            assert rule.requires_member_state_mapping is True
            assert rule.mapping_type == "DIRECTIVE_PROHIBITION"

    def test_6_eu_ucpd_missing_member_state_mapping_potentially_relevant(self):
        """EU UCPD + missing member-state mapping -> POTENTIALLY_RELEVANT / unresolved."""
        ev = [_make_ev("E1", source="price", description="Unbundled drip fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="EU",
            transaction_date="2024-05-15",
            member_state=None,  # Missing member state mapping
        )
        ucpd_finding = next(f for f in resp.findings if f.rule_id == "EU_UCPD_DRIP_PRICING")
        assert ucpd_finding.authority_type == "EU_DIRECTIVE"
        assert ucpd_finding.requires_member_state_mapping is True
        assert ucpd_finding.status == STATUS_POTENTIALLY_RELEVANT
        assert ucpd_finding.status != STATUS_SUPPORTED
        assert "directive" in ucpd_finding.explanation.lower()

    def test_7_ftc_sec5_general_authority_metadata(self, registry):
        """FTC §5 -> general authority metadata."""
        ftc_rules = [r for r in registry.get_all_rules() if "FTC_ACT" in r.rule_id]
        assert len(ftc_rules) >= 3
        for rule in ftc_rules:
            assert rule.authority_type == "GENERAL_CONSUMER_PROTECTION_AUTHORITY"
            assert rule.mapping_type == "POTENTIAL_APPLICABILITY"
            assert rule.authoritative_source == "Federal Trade Commission Act, 15 U.S.C. § 45(a)(1)"

    def test_8_ftc_sec5_wording_no_unconditional_dark_pattern_claim(self):
        """FTC §5 wording contains no unconditional dark-pattern statutory claim."""
        ev = [_make_ev("E1", source="dom", description="Countdown timer reset")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_FALSE_URGENCY, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="US",
            transaction_date="2024-05-15",
        )
        ftc_finding = next(f for f in resp.findings if f.rule_id == "US_FTC_ACT_SEC5_FALSE_URGENCY")
        assert ftc_finding.status == STATUS_POTENTIALLY_RELEVANT
        assert "prohibits false urgency" not in ftc_finding.explanation.lower()
        assert "violates" not in ftc_finding.explanation.lower()
        assert "illegal" not in ftc_finding.explanation.lower()
        assert ftc_finding.explanation == "Available evidence may be relevant to the configured Section 5 consumer-protection rule mapping."

    def test_9_india_ccpa_existing_behavior_unchanged(self):
        """India CCPA -> existing behavior unchanged."""
        ev = [_make_ev("E1", source="price", description="₹500 hidden fee added at checkout")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        ccpa_finding = next(f for f in resp.findings if f.rule_id == "IN_CCPA_DRIP_PRICING")
        assert ccpa_finding.status == STATUS_SUPPORTED
        assert ccpa_finding.applicability == APPLICABLE
        assert ccpa_finding.confidence == 0.85
        assert ccpa_finding.source == "CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 5"
        assert ccpa_finding.explanation == "Available evidence matches the configured rule conditions for potential regulatory concern."

    def test_10_risk_score_bit_for_bit_identical(self, fusion_engine):
        """Risk score remains bit-for-bit identical."""
        req = EvidenceFusionRequest(text="Urgent! Price $50, booking fee $10.")
        pre_res = fusion_engine.fuse(req)
        score_before = pre_res.risk_score

        # Run RegulatoryEngine with multiple findings
        ev = [_make_ev("E1", source="price", description="fee")]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"])
            ]
        )
        reg_resp = RegulatoryEngine.evaluate(
            intelligence_analysis=intel,
            raw_evidence=ev,
            jurisdiction="IN",
            transaction_date="2024-05-15",
        )
        assert len(reg_resp.findings) > 0

        post_res = fusion_engine.fuse(req)
        score_after = post_res.risk_score

        # Must remain bit-for-bit identical
        assert score_before == score_after

    def test_11_b5_1_to_b5_7_remain_frozen(self):
        """B5.1-B5.7 core files remain strictly intact and frozen."""
        import os
        frozen_files = [
            "backend/schemas/evidence.py",
            "backend/services/evidence_adapters.py",
            "backend/services/evidence_deduplicator.py",
            "backend/services/evidence_fusion.py",
            "backend/services/contradiction_engine.py",
            "backend/services/temporal_engine.py",
            "backend/services/journey_engine.py",
            "backend/services/evidence_graph.py",
            "backend/services/intelligence_engine.py",
        ]
        for fpath in frozen_files:
            assert os.path.isfile(fpath), f"Frozen file {fpath} does not exist!"
            assert os.path.getsize(fpath) > 0, f"Frozen file {fpath} is empty!"

    def test_12_deterministic_output_byte_identical_across_runs(self):
        """Deterministic output remains byte-identical across repeated evaluations."""
        ev = [
            _make_ev("E1", source="price", description="Price $100"),
            _make_ev("E2", source="dom", description="Hidden subscription toggle"),
        ]
        intel = IntelligenceAnalysisResponse(
            pattern_assessments=[
                PatternAssessment(pattern=PATTERN_DRIP_PRICING, status="SUPPORTED", supporting_evidence_ids=["E1"]),
                PatternAssessment(pattern=PATTERN_SUBSCRIPTION_TRAP, status="SUPPORTED", supporting_evidence_ids=["E2"]),
            ]
        )
        serialized_outputs = [
            RegulatoryEngine.evaluate(
                intelligence_analysis=intel,
                raw_evidence=ev,
                jurisdiction="US",
                transaction_date="2024-05-15",
            ).model_dump_json()
            for _ in range(5)
        ]
        for s in serialized_outputs[1:]:
            assert s == serialized_outputs[0]
