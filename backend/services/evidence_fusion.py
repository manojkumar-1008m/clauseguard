"""backend/services/evidence_fusion.py
Service-layer Evidence Fusion Engine for ClauseGuard (Phase 8.6).
Combines independent evidence from Text Predictor, Price Analyzer, UI/DOM,
and behavior signals into a unified, traceable evidence structure.
Enforces deterministic scoring, provenance preservation, anti-double-counting,
and strict separation between financial signals and dark-pattern judgments.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ..schemas.evidence import (
    ConsumerConsequence,
    ContradictionItem,
    CONTEXT_FAMILY_MAP,
    EvidenceConflict,
    EvidenceFusionRequest,
    EvidenceFusionResponse,
    EvidenceGroup,
    EvidenceItem,
    FinancialImpact,
    TemporalRelationshipItem,
)
from ..schemas.price import PriceAnalysisResponse
from ..schemas import PredictResponse
from .contradiction_engine import ContradictionEngine
from .evidence_deduplicator import EvidenceDeduplicator
from .evidence_graph import EvidenceGraph
from .price_analyzer import PriceAnalyzer
from .temporal_engine import TemporalEngine
from .text_predictor import TextPredictor
from .intelligence_engine import IntelligenceEngine
from .evidence_adapters import (
    adapt_behavior_evidence,
    adapt_dom_evidence,
    adapt_image_evidence,
    adapt_price_analysis,
    adapt_text_prediction,
    normalize_decision_context,
)

_logger = logging.getLogger("clauseguard_backend.evidence_fusion")

# Deterministic scoring constants (documented engineering baseline)
WEAK_SIGNAL_SCORE: float = 1.0
MODERATE_SIGNAL_SCORE: float = 2.0
STRONG_SIGNAL_SCORE: float = 3.0
CORROBORATION_BONUS: float = 2.0
MULTI_SOURCE_BONUS: float = 1.0
CONFLICT_PENALTY: float = 1.0

# Risk level thresholds
RISK_THRESHOLD_MEDIUM: float = 3.0
RISK_THRESHOLD_HIGH: float = 5.0
RISK_THRESHOLD_CRITICAL: float = 8.0

STANDARD_PATTERN_NAMES: Dict[str, str] = {
    "subscription_trap": "Subscription Trap",
    "drip_pricing": "Drip Pricing",
    "urgency": "Urgency",
    "scarcity": "Scarcity",
    "social_proof": "Social Proof",
    "obstruction": "Obstruction",
    "sneaking": "Sneaking",
    "confirm_shaming": "Confirm Shaming",
    "forced_action": "Forced Action",
    "misdirection": "Misdirection",
}


def _extract_signals(
    text_prediction: Optional[PredictResponse],
    price_analysis: Optional[PriceAnalysisResponse],
    evidence_items: List[EvidenceItem],
    is_corroborated: bool = False,
    raw_text: Optional[str] = None,
) -> List[str]:
    """Extract structured, observable signals from upstream analyzers deterministically."""
    signals: List[str] = []

    # Text signals
    if text_prediction:
        if text_prediction.prediction == 1:
            signals.append("text:dark_pattern_detected")
            if text_prediction.pattern_category:
                signals.append(f"text:pattern:{text_prediction.pattern_category}")
            if text_prediction.requires_context:
                signals.append("text:requires_context")
            if text_prediction.confidence is not None:
                signals.append(f"text:confidence:{text_prediction.confidence:.2f}")
        else:
            signals.append("text:not_dark_pattern")

    # Price signals
    if price_analysis:
        if price_analysis.displayed_price is not None:
            signals.append("price:displayed_price")
        if price_analysis.trial_price is not None:
            signals.append("price:trial_price")
        if price_analysis.renewal_price is not None or price_analysis.renewal_price_detected:
            signals.append("price:renewal_price")
        if price_analysis.recurring:
            signals.append("price:recurring_billing")
        if price_analysis.additional_cost is not None or price_analysis.additional_cost_detected or price_analysis.additional_costs is not None:
            signals.append("price:additional_cost")
        if price_analysis.late_disclosed is True or price_analysis.late_disclosure_detected:
            signals.append("price:late_disclosure")
        has_actual_change = bool(
            not price_analysis.is_alternative_pricing
            and (
                price_analysis.price_change_detected
                or price_analysis.price_changed
                or (price_analysis.price_change is not None and price_analysis.price_change != 0.0)
            )
            and (price_analysis.price_change != 0.0 if price_analysis.price_change is not None else True)
        )
        if has_actual_change:
            signals.append("price:price_changed")
            if price_analysis.price_change_direction:
                signals.append(f"price:direction:{price_analysis.price_change_direction}")
        if price_analysis.explicit_total is not None:
            signals.append("price:explicit_total")
        if price_analysis.is_alternative_pricing:
            signals.append("price:alternative_pricing")
        if price_analysis.discount_amount is not None:
            signals.append("price:discount")
        if raw_text and ("including" in raw_text.lower() or "inclusive" in raw_text.lower()) and not (price_analysis.late_disclosed or price_analysis.late_disclosure_detected):
            signals.append("price:inclusive_pricing")

    # DOM signals
    for item in evidence_items:
        if item.source == "dom" and item.detected:
            signals.append(f"dom:{item.type}")
            if item.decision_context:
                signals.append(f"dom:context:{item.decision_context}")
            if item.element_ref:
                signals.append(f"dom:element:{item.element_ref}")
            if item.strength:
                signals.append(f"dom:strength:{item.strength}")

    # Behavior signals
    for item in evidence_items:
        if item.source == "behavior" and item.detected:
            signals.append(f"behavior:{item.type}")
            if item.decision_context:
                signals.append(f"behavior:context:{item.decision_context}")
            if item.strength:
                signals.append(f"behavior:strength:{item.strength}")
            if item.route:
                signals.append(f"behavior:route:{item.route}")

    # Fusion signals
    if is_corroborated:
        signals.append("fusion:corroborated")

    # Deduplicate signals preserving order
    seen_sigs = set()
    deduped_sigs: List[str] = []
    for s in signals:
        if s not in seen_sigs:
            seen_sigs.add(s)
            deduped_sigs.append(s)

    return deduped_sigs


def _partition_by_journey(items: List[EvidenceItem]) -> Dict[str, List[EvidenceItem]]:
    """Partition items by journey_id, isolating auxiliary items and separate journeys (Part 17).

    If journey_id is absent, fallback to session_id or '__legacy__'.
    Auxiliary items receive a unique non-correlating key '__auxiliary_<eid>__'.
    """
    partitions: Dict[str, List[EvidenceItem]] = {}
    for item in items:
        if getattr(item, "is_auxiliary", False):
            key = f"__auxiliary_{item.evidence_id}__"
        elif item.journey_id:
            key = f"jrn_{item.journey_id}"
        else:
            meta = item.metadata or {}
            sess = meta.get("session_id")
            key = f"sess_{sess}" if sess else "__legacy__"

        if key not in partitions:
            partitions[key] = []
        partitions[key].append(item)
    return partitions


class EvidenceFusionEngine:
    """Deterministic Evidence Fusion Engine combining signals across analyzers."""

    def __init__(
        self,
        text_predictor: Optional[TextPredictor] = None,
        price_analyzer: Optional[PriceAnalyzer] = None,
        contradiction_engine: Optional[ContradictionEngine] = None,
        temporal_engine: Optional[TemporalEngine] = None,
        evidence_deduplicator: Optional[EvidenceDeduplicator] = None,
    ):
        self.text_predictor = text_predictor or TextPredictor()
        self.price_analyzer = price_analyzer or PriceAnalyzer()
        self.contradiction_engine = contradiction_engine or ContradictionEngine()
        self.temporal_engine = temporal_engine or TemporalEngine()
        self.evidence_deduplicator = evidence_deduplicator or EvidenceDeduplicator()

    def fuse(self, request: EvidenceFusionRequest) -> EvidenceFusionResponse:
        """Fuse multi-source evidence into a structured risk representation."""
        evidence_items: List[EvidenceItem] = []
        conflicts: List[EvidenceConflict] = []
        counter = 1

        def next_id() -> str:
            nonlocal counter
            eid = f"E{counter:03d}"
            counter += 1
            return eid

        # 1. Obtain analyzer outputs
        text_prediction = request.text_prediction
        price_analysis = request.price_analysis
        raw_text = request.text

        if raw_text and not text_prediction:
            try:
                text_prediction = self.text_predictor.predict(raw_text)
            except Exception as exc:
                _logger.warning("Text predictor execution failed during fusion: %s", exc)

        if raw_text and not price_analysis:
            try:
                price_analysis = self.price_analyzer.analyze(raw_text)
            except Exception as exc:
                _logger.warning("Price analyzer execution failed during fusion: %s", exc)

        # 2. Extract Text Evidence
        has_context_required = False
        text_requires_context = False
        has_text_sub = False
        has_text_drip = False
        has_text_urgency = False
        has_text_scarcity = False
        has_text_social_proof = False

        if text_prediction and text_prediction.prediction == 1:
            raw_cat = text_prediction.pattern_category or "potential_dark_pattern"
            pat = raw_cat.lower().replace(" ", "_")
            req_ctx = bool(text_prediction.requires_context)
            text_requires_context = req_ctx
            has_context_required = req_ctx

            if "subscription" in pat or pat == "subscription_trap":
                has_text_sub = True
            elif "drip" in pat or pat == "drip_pricing":
                has_text_drip = True
            elif "urgency" in pat:
                has_text_urgency = True
            elif "scarcity" in pat:
                has_text_scarcity = True
            elif "social_proof" in pat:
                has_text_social_proof = True

            evidence_items.extend(
                adapt_text_prediction(
                    prediction=text_prediction,
                    raw_text=raw_text,
                    next_id_fn=next_id,
                )
            )

        # 3. Extract Price Evidence
        if price_analysis:
            evidence_items.extend(
                adapt_price_analysis(
                    analysis=price_analysis,
                    has_text_sub=has_text_sub,
                    has_text_drip=has_text_drip,
                    next_id_fn=next_id,
                )
            )

        # 4. Ingest external DOM / UI / behavior / image / raw evidence (Part 10, 11, 12)
        request_is_auxiliary = bool(
            request.raw_evidence and all(getattr(e, "is_auxiliary", False) for e in request.raw_evidence)
        )
        if request.dom_evidence:
            evidence_items.extend(adapt_dom_evidence(request.dom_evidence, next_id_fn=next_id))
        if request.ui_evidence:
            evidence_items.extend(adapt_dom_evidence(request.ui_evidence, next_id_fn=next_id))
        if request.behavior_evidence:
            evidence_items.extend(adapt_behavior_evidence(request.behavior_evidence, next_id_fn=next_id))
        if request.image_evidence:
            evidence_items.extend(adapt_image_evidence(request.image_evidence, next_id_fn=next_id))
        if request.raw_evidence:
            for ext_item in request.raw_evidence:
                item_copy = ext_item.model_copy() if hasattr(ext_item, "model_copy") else ext_item.copy()
                if not item_copy.evidence_id:
                    item_copy.evidence_id = next_id()
                evidence_items.append(item_copy)

        if request_is_auxiliary:
            for itm in evidence_items:
                itm.is_auxiliary = True

        all_input_observations = list(evidence_items)

        # 5. Contradiction & Temporal Detection (Phase B5.3)
        contradictions = self.contradiction_engine.detect_contradictions(
            evidence_items=evidence_items,
            raw_text=raw_text,
            text_prediction=text_prediction,
            price_analysis=price_analysis,
        )

        temporal_relationships = self.temporal_engine.detect_temporal_relationships(
            evidence_items=evidence_items,
            price_analysis=price_analysis,
        )

        # 6. Phase B5.5 Evidence Graph Construction & Cross-Source Deduplication
        graph, scoring_evidence = self.evidence_deduplicator.build_evidence_graph(
            evidence_items=all_input_observations,
            contradictions=contradictions,
        )

        # Populate event_node_id on items
        for item in all_input_observations:
            ev_node = graph.get_event_for_evidence(item.evidence_id)
            if ev_node:
                item.event_node_id = ev_node.node_id

        # Downstream grouping and scoring uses deduplicated canonical evidence
        evidence_items = scoring_evidence

        # Legacy conflict detection for backward compatibility
        # A. Text claims free trial, but pricing reports paid trial
        has_text_free_claim = any(
            e.source == "text" and not getattr(e, "is_auxiliary", False) and "free" in (e.description or "").lower() and "trial" in (e.description or "").lower()
            for e in evidence_items
        ) or (raw_text and "free trial" in raw_text.lower())

        has_paid_trial = any(
            e.source == "price" and not getattr(e, "is_auxiliary", False) and e.type == "paid_trial" and e.value and e.value > 0
            for e in evidence_items
        )

        if has_text_free_claim and has_paid_trial:
            text_items_free = [e for e in evidence_items if e.source == "text" and not getattr(e, "is_auxiliary", False)]
            price_items_paid = [e for e in evidence_items if e.source == "price" and not getattr(e, "is_auxiliary", False) and e.type == "paid_trial"]
            t_jrn = text_items_free[0].journey_id if text_items_free else None
            p_jrn = price_items_paid[0].journey_id if price_items_paid else None
            if not (t_jrn and p_jrn and t_jrn != p_jrn):
                conflicts.append(
                    EvidenceConflict(
                        type="evidence_conflict",
                        sources=["text", "price"],
                        description="Text states or implies a free trial, but price analyzer detected an explicit paid trial amount",
                        resolution="preserve_both",
                    )
                )

        # B. Text claims one-time payment, but price indicates recurring renewal
        has_one_time_claim = (raw_text and any(k in raw_text.lower() for k in ["one-time payment", "single payment", "one time fee"]))
        has_recurring_price = any(e.source == "price" and not getattr(e, "is_auxiliary", False) and e.type == "renewal_price" for e in evidence_items)
        if has_one_time_claim and has_recurring_price:
            text_items_ot = [e for e in evidence_items if e.source == "text" and not getattr(e, "is_auxiliary", False)]
            price_items_rec = [e for e in evidence_items if e.source == "price" and not getattr(e, "is_auxiliary", False) and e.type == "renewal_price"]
            t_jrn = text_items_ot[0].journey_id if text_items_ot else None
            p_jrn = price_items_rec[0].journey_id if price_items_rec else None
            if not (t_jrn and p_jrn and t_jrn != p_jrn):
                conflicts.append(
                    EvidenceConflict(
                        type="evidence_conflict",
                        sources=["text", "price"],
                        description="Text suggests one-time payment, but price analysis identified an ongoing recurring renewal",
                        resolution="preserve_both",
                    )
                )

        # Mirror any new semantic contradictions into conflicts
        for c in contradictions:
            if not any(set(conf.sources) == {c.source_a, c.source_b} and conf.type == c.type for conf in conflicts):
                conflicts.append(
                    EvidenceConflict(
                        type=c.type,
                        sources=[c.source_a, c.source_b],
                        description=c.reason,
                        resolution="preserve_both",
                    )
                )

        # 7. Form Evidence Groups & Detect Cross-Source Corroboration
        evidence_groups: List[EvidenceGroup] = []
        group_counter = 1

        def next_gid() -> str:
            nonlocal group_counter
            gid = f"G{group_counter:03d}"
            group_counter += 1
            return gid

        assigned_eids: Set[str] = set()

        # Group A: Subscription / Cancellation Risk
        sub_text_items = [
            e for e in evidence_items
            if e.source == "text" and (e.pattern in ("subscription_trap", "subscription") or "subscription" in (e.pattern or ""))
            and e.evidence_id not in assigned_eids
        ]
        sub_price_items = [
            e for e in evidence_items
            if e.source == "price" and e.type in ("renewal_price", "free_trial", "paid_trial")
            and e.evidence_id not in assigned_eids
        ]
        sub_dom_items = [
            e for e in evidence_items
            if e.source == "dom" and (
                e.decision_context in ("cancellation", "subscription", "membership", "renewal")
                or (e.decision_context is None and e.pattern == "subscription_trap")
            ) and (
                e.pattern in ("subscription_trap", "obstruction")
                or e.type in (
                    "cancel_action_visually_deemphasized", "action_visual_deemphasis",
                    "cancel_action_disabled", "disabled_action",
                    "hidden_alternative", "hidden_action", "covered_action",
                    "confirmation_ui", "modal_interference", "scroll_lock_interference",
                    "cancellation_obstruction"
                )
            )
            and e.evidence_id not in assigned_eids
        ]
        sub_beh_items = [
            e for e in evidence_items
            if e.source == "behavior" and (
                e.decision_context in ("cancellation", "subscription", "membership", "renewal")
                or (e.decision_context is None and e.pattern == "subscription_trap")
            ) and (
                e.pattern in ("subscription_trap", "obstruction", "forced_action")
                or e.type in (
                    "repeated_retention_interference", "retention_friction", "repeated_retention",
                    "cancellation_obstruction", "cancellation_abandonment",
                    "repeated_confirmation_pressure", "repeated_confirmation_friction",
                    "backtracking_loop", "dead_end_behavior", "forced_delay",
                    "required_survey", "survey_wall_friction", "forced_action_sequence"
                )
            )
            and e.evidence_id not in assigned_eids
        ]
        sub_items = sub_text_items + sub_price_items + sub_dom_items + sub_beh_items
        if sub_items:
            for j_key, j_sub_items in _partition_by_journey(sub_items).items():
                if not j_sub_items:
                    continue
                is_aux = j_key.startswith("__auxiliary_")
                j_t = [e for e in j_sub_items if e.source == "text"]
                j_p = [e for e in j_sub_items if e.source == "price"]
                j_d = [e for e in j_sub_items if e.source == "dom"]
                j_b = [e for e in j_sub_items if e.source == "behavior"]
                sources = sorted(list({e.source for e in j_sub_items}))
                corrob_sources: Set[str] = set()
                if not is_aux:
                    if j_t and not text_requires_context:
                        corrob_sources.add("text")
                    if j_p and (j_t or j_d or j_b):
                        corrob_sources.add("price")
                    if j_d and any(e.strength in ("strong", "moderate") for e in j_d):
                        corrob_sources.add("dom")
                    if j_b and any(e.strength in ("strong", "moderate") for e in j_b):
                        corrob_sources.add("behavior")

                is_corrob = len(corrob_sources) >= 2 and not is_aux
                if j_t or j_p or any(e.pattern == "subscription_trap" for e in j_sub_items):
                    grp_pattern = "subscription_trap"
                    desc = "Corroborated subscription risk: recurring commitment supported by multiple sources" if is_corrob else "Subscription structure detected"
                else:
                    grp_pattern = "obstruction"
                    desc = "Corroborated cancellation obstruction across interfaces" if is_corrob else "Cancellation friction detected"

                if is_aux:
                    desc = f"Auxiliary context: {desc}"

                evidence_groups.append(
                    EvidenceGroup(
                        group_id=next_gid(),
                        pattern=grp_pattern,
                        evidence_ids=[e.evidence_id for e in j_sub_items],
                        sources=sources,
                        corroborated=is_corrob,
                        description=desc,
                    )
                )
                for e in j_sub_items:
                    assigned_eids.add(e.evidence_id)

        # Group B: Price Disclosure / Drip Pricing / Sneaking Risk
        drip_text_items = [
            e for e in evidence_items
            if e.source == "text" and (e.pattern in ("drip_pricing", "hidden_fee", "hidden_cost") or "drip" in (e.pattern or ""))
            and e.evidence_id not in assigned_eids
        ]
        drip_price_items = [
            e for e in evidence_items
            if e.source == "price" and e.type in ("additional_cost", "late_disclosure")
            and e.evidence_id not in assigned_eids
        ]
        drip_dom_items = [
            e for e in evidence_items
            if e.source == "dom" and (
                e.type in ("post_action_fee_added", "post_action_price_changed", "preselected_option", "preselected_commercial_choice")
                or e.pattern in ("drip_pricing", "sneaking")
            ) and (e.decision_context in ("checkout", "billing", "purchase", "cart", None))
            and e.evidence_id not in assigned_eids
        ]
        drip_items = drip_text_items + drip_price_items + drip_dom_items
        if drip_items:
            for j_key, j_drip_items in _partition_by_journey(drip_items).items():
                if not j_drip_items:
                    continue
                is_aux = j_key.startswith("__auxiliary_")
                j_t = [e for e in j_drip_items if e.source == "text"]
                j_p = [e for e in j_drip_items if e.source == "price"]
                j_d = [e for e in j_drip_items if e.source == "dom"]

                sources = sorted(list({e.source for e in j_drip_items}))
                corrob_sources = set()
                if not is_aux:
                    if j_t and not text_requires_context:
                        corrob_sources.add("text")
                    has_late_fee = any(e.type == "late_disclosure" for e in j_p) or bool(
                        price_analysis and (price_analysis.late_disclosed or price_analysis.late_disclosure_detected) and (price_analysis.additional_cost is not None or price_analysis.additional_costs is not None or price_analysis.additional_cost_detected)
                    )
                    if has_late_fee or (j_p and j_d):
                        corrob_sources.add("price")
                    if j_d and any(e.strength in ("strong", "moderate") for e in j_d):
                        corrob_sources.add("dom")

                is_corrob = len(corrob_sources) >= 2 and not is_aux

                if any(e.pattern == "sneaking" or e.type.startswith("preselected_") for e in j_drip_items) and not (j_t or j_p):
                    grp_pattern = "sneaking"
                    desc = "Preselected commercial choice detected"
                else:
                    grp_pattern = "drip_pricing"
                    desc = "Corroborated price disclosure risk: hidden fee verified across sources" if is_corrob else "Price disclosure relationship detected"

                if is_aux:
                    desc = f"Auxiliary context: {desc}"

                evidence_groups.append(
                    EvidenceGroup(
                        group_id=next_gid(),
                        pattern=grp_pattern,
                        evidence_ids=[e.evidence_id for e in j_drip_items],
                        sources=sources,
                        corroborated=is_corrob,
                        description=desc,
                    )
                )
                for e in j_drip_items:
                    assigned_eids.add(e.evidence_id)

        # Group C: Urgency / Scarcity / Social Proof Risk
        urgency_items = [
            e for e in evidence_items
            if (e.pattern in {"urgency", "scarcity", "social_proof"} or e.type in {"urgency", "scarcity", "countdown_timer", "fake_countdown_structure"})
            and e.evidence_id not in assigned_eids
        ]
        if urgency_items:
            for j_key, j_urgency_items in _partition_by_journey(urgency_items).items():
                if not j_urgency_items:
                    continue
                is_aux = j_key.startswith("__auxiliary_")
                sources = sorted(list({e.source for e in j_urgency_items}))
                corrob_sources = set(sources)
                if text_requires_context or is_aux:
                    corrob_sources.discard("text")
                is_corrob = len(corrob_sources) >= 2 and not is_aux
                grp_pattern = j_urgency_items[0].pattern or j_urgency_items[0].type
                desc = "Corroborated pressure signal across interfaces" if is_corrob else f"Interface {grp_pattern} indicator"
                if is_aux:
                    desc = f"Auxiliary context: {desc}"
                evidence_groups.append(
                    EvidenceGroup(
                        group_id=next_gid(),
                        pattern=grp_pattern,
                        evidence_ids=[e.evidence_id for e in j_urgency_items],
                        sources=sources,
                        corroborated=is_corrob,
                        description=desc,
                    )
                )
                for e in j_urgency_items:
                    assigned_eids.add(e.evidence_id)

        # Group D: Standalone Obstruction / Forced Action (Context-Aware Grouping)
        obstruction_items = [
            e for e in evidence_items
            if (e.pattern in ("obstruction", "forced_action") or e.type in (
                "action_visual_deemphasis", "cancel_action_visually_deemphasized",
                "disabled_action", "cancel_action_disabled",
                "repeated_retention_interference", "required_survey", "backtracking_loop",
                "cancellation_obstruction", "forced_action_sequence"
            ))
            and e.evidence_id not in assigned_eids
        ]
        if obstruction_items:
            # Partition candidates into compatible context families
            fam_groups: Dict[str, List[EvidenceItem]] = {}
            for e in obstruction_items:
                ctx_clean = (e.decision_context or "unknown").strip().lower()
                fam = CONTEXT_FAMILY_MAP.get(ctx_clean, "unknown_family")
                if fam not in fam_groups:
                    fam_groups[fam] = []
                fam_groups[fam].append(e)

            for fam, cluster in fam_groups.items():
                if not cluster:
                    continue
                for j_key, j_cluster in _partition_by_journey(cluster).items():
                    if not j_cluster:
                        continue
                    is_aux = j_key.startswith("__auxiliary_")
                    sources = sorted(list({e.source for e in j_cluster}))
                    corrob_sources = set(sources)
                    if text_requires_context or is_aux:
                        corrob_sources.discard("text")
                    is_corrob = len(corrob_sources) >= 2 and not is_aux
                    grp_pattern = j_cluster[0].pattern or "obstruction"
                    desc = "Corroborated obstruction/friction across observable channels" if is_corrob else f"Observable interface {grp_pattern}"
                    if is_aux:
                        desc = f"Auxiliary context: {desc}"
                    evidence_groups.append(
                        EvidenceGroup(
                            group_id=next_gid(),
                            pattern=grp_pattern,
                            evidence_ids=[e.evidence_id for e in j_cluster],
                            sources=sources,
                            corroborated=is_corrob,
                            description=desc,
                        )
                    )
                    for e in j_cluster:
                        assigned_eids.add(e.evidence_id)

        # Group E: Standalone Misdirection / Sneaking / Confirm Shaming
        ui_asymmetry_items = [
            e for e in evidence_items
            if (e.pattern in ("misdirection", "sneaking", "confirm_shaming") or e.type in (
                "action_size_asymmetry", "contrast_asymmetry", "typography_asymmetry",
                "visibility_mismatch", "semantic_competing_actions", "preselected_option",
                "preselected_commercial_choice", "asymmetric_confirmation"
            ))
            and e.evidence_id not in assigned_eids
        ]
        if ui_asymmetry_items:
            for j_key, j_ui_items in _partition_by_journey(ui_asymmetry_items).items():
                if not j_ui_items:
                    continue
                is_aux = j_key.startswith("__auxiliary_")
                sources = sorted(list({e.source for e in j_ui_items}))
                corrob_sources = set(sources)
                if text_requires_context or is_aux:
                    corrob_sources.discard("text")
                is_corrob = len(corrob_sources) >= 2 and not is_aux
                grp_pattern = j_ui_items[0].pattern or "misdirection"
                desc = f"Observable interface {grp_pattern}"
                if is_aux:
                    desc = f"Auxiliary context: {desc}"
                evidence_groups.append(
                    EvidenceGroup(
                        group_id=next_gid(),
                        pattern=grp_pattern,
                        evidence_ids=[e.evidence_id for e in j_ui_items],
                        sources=sources,
                        corroborated=is_corrob,
                        description=desc,
                    )
                )
                for e in j_ui_items:
                    assigned_eids.add(e.evidence_id)

        # Group F: Price Change (Pure Financial Signal)
        change_items = [e for e in evidence_items if e.type == "price_change" and e.evidence_id not in assigned_eids]
        if change_items:
            sources = sorted(list({e.source for e in change_items}))
            evidence_groups.append(
                EvidenceGroup(
                    group_id=next_gid(),
                    pattern="price_change",
                    evidence_ids=[e.evidence_id for e in change_items],
                    sources=sources,
                    corroborated=False,
                    description="Explicit price change transaction",
                )
            )
            for e in change_items:
                assigned_eids.add(e.evidence_id)

        # Group G: Remaining unassigned items (e.g. displayed_price)
        unassigned = [e for e in evidence_items if e.evidence_id not in assigned_eids]
        for item in unassigned:
            evidence_groups.append(
                EvidenceGroup(
                    group_id=next_gid(),
                    pattern=item.pattern or item.type,
                    evidence_ids=[item.evidence_id],
                    sources=[item.source],
                    corroborated=False,
                    description=item.description,
                )
            )

        # 8. Deterministic Scoring
        # Distinguish financial facts from dark-pattern evidence
        score = 0.0

        # Filter out auxiliary evidence from scoring (Part 12)
        scoring_evidence = [e for e in evidence_items if not getattr(e, "is_auxiliary", False)]
        all_auxiliary = bool(evidence_items and len(scoring_evidence) == 0)

        # Text contribution
        text_items = [e for e in scoring_evidence if e.source == "text"]
        if text_items:
            if text_requires_context:
                score += WEAK_SIGNAL_SCORE  # 1.0 (context-required penalty)
            else:
                score += MODERATE_SIGNAL_SCORE  # 2.0

        # Price contribution (evaluated per distinct financial reality)
        has_renewal = any(e.type == "renewal_price" for e in scoring_evidence)
        has_free_trial = any(e.type == "free_trial" for e in scoring_evidence)
        has_add_cost = any(e.type == "additional_cost" for e in scoring_evidence)
        has_late_disc = any(e.type == "late_disclosure" for e in scoring_evidence)
        has_p_change = any(e.type == "price_change" for e in scoring_evidence)

        # Related price supporting text (Section 17: RELATED PRICE supporting TEXT: +2)
        if not text_requires_context and has_text_sub and (has_renewal or has_free_trial):
            score += MODERATE_SIGNAL_SCORE  # +2.0
            if has_renewal and has_free_trial:
                score += WEAK_SIGNAL_SCORE  # +1.0 (additional supporting financial fact: trial + renewal)
        elif not text_requires_context and has_text_drip and has_late_disc and has_add_cost:
            score += MODERATE_SIGNAL_SCORE  # +2.0
        elif not text_items or text_requires_context:
            # Pure financial signals without dark pattern text (or when text requires context)
            if has_renewal and has_free_trial:
                score += MODERATE_SIGNAL_SCORE  # 2.0 (financial notice: trial + renewal)
            elif has_renewal:
                score += WEAK_SIGNAL_SCORE  # 1.0
            elif has_free_trial:
                score += WEAK_SIGNAL_SCORE  # 1.0
            elif has_add_cost and has_late_disc:
                score += MODERATE_SIGNAL_SCORE  # 2.0 (financial notice: late fee)
            elif has_add_cost:
                score += WEAK_SIGNAL_SCORE  # 1.0
            elif has_p_change:
                score += WEAK_SIGNAL_SCORE  # 1.0 (pure financial price change)

        # DOM contribution (Step 1, 4, 8: bounded, deterministic strength mapping)
        EVIDENCE_STRENGTH_WEIGHTS = {
            "strong": 1.0,
            "moderate": 0.65,
            "weak": 0.30,
            "insufficient": 0.0,
        }
        dom_items = [e for e in scoring_evidence if e.source == "dom" and e.detected]
        dom_contribs = [
            EVIDENCE_STRENGTH_WEIGHTS.get(e.strength, 0.5) * 3.0
            for e in dom_items
        ]
        dom_score = min(3.5, sum(dom_contribs)) if dom_contribs else 0.0
        score += dom_score

        # Behavior contribution (Step 2, 4, 8: bounded, deterministic strength mapping)
        beh_items = [e for e in scoring_evidence if e.source == "behavior" and e.detected]
        beh_contribs = [
            EVIDENCE_STRENGTH_WEIGHTS.get(e.strength, 0.5) * 3.0
            for e in beh_items
        ]
        beh_score = min(3.5, sum(beh_contribs)) if beh_contribs else 0.0
        score += beh_score

        # Corroboration bonus: awarded ONLY when true semantic cross-source corroboration exists
        has_corroboration = any(g.corroborated for g in evidence_groups)
        if has_corroboration:
            score += CORROBORATION_BONUS  # +2.0
            score += MULTI_SOURCE_BONUS   # +1.0

        # Contradiction escalation: bounded contribution representing consumer risk (Phase B5.3 Part H)
        contradiction_escalation = self.contradiction_engine.compute_contradiction_escalation(
            contradictions=contradictions,
            evidence_groups=evidence_groups,
        )
        score += contradiction_escalation

        # Legacy conflict penalty for direct statement contradictions
        has_direct_statement_conflict = (has_text_free_claim and has_paid_trial) or (has_one_time_claim and has_recurring_price)
        if has_direct_statement_conflict:
            score -= CONFLICT_PENALTY

        # Global fusion score ceiling: enforce deterministic [0.0, 10.0] risk scale (Fix 3)
        score = min(10.0, max(0.0, score))

        # Evaluate strong non-text signals for source-scoped context (Step 7)
        has_strong_dom = any(e.source == "dom" and e.strength == "strong" and e.detected for e in scoring_evidence)
        has_strong_beh = any(e.source == "behavior" and e.strength == "strong" and e.detected for e in scoring_evidence)
        has_strong_non_text = has_strong_dom or has_strong_beh
        has_non_text_corrob = any(
            g.corroborated and not (len(g.sources) == 1 and "text" in g.sources)
            for g in evidence_groups
            if any(s in ("dom", "behavior", "price") for s in g.sources)
        )

        # Risk Level Resolution
        if text_requires_context and not (has_strong_non_text or has_non_text_corrob):
            risk_level = "LOW"
        elif score >= RISK_THRESHOLD_CRITICAL:
            risk_level = "CRITICAL"
        elif score >= RISK_THRESHOLD_HIGH:
            risk_level = "HIGH"
        elif score >= RISK_THRESHOLD_MEDIUM:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Confidence Calculation
        confidence: Optional[float] = None
        if evidence_items:
            base_conf = max((e.confidence for e in evidence_items if e.confidence is not None), default=0.70)
            if has_corroboration:
                base_conf = min(0.95, base_conf + 0.15)
            if text_requires_context and not (has_strong_non_text or has_non_text_corrob):
                base_conf = max(0.20, base_conf - 0.15)
            if conflicts:
                base_conf = max(0.15, base_conf - 0.20)
            confidence = round(base_conf, 2)

        # 9. Consumer Consequence & Financial Impact
        financial_impact: Optional[FinancialImpact] = None
        if price_analysis and not all_auxiliary:
            financial_impact = FinancialImpact(
                initial_price=price_analysis.displayed_price.amount if price_analysis.displayed_price else price_analysis.initial_price,
                additional_cost=price_analysis.additional_cost if price_analysis.additional_cost is not None else price_analysis.additional_costs,
                known_total=price_analysis.known_total,
                additional_cost_percentage=price_analysis.additional_cost_percentage,
                trial_price=price_analysis.trial_price,
                trial_duration_days=price_analysis.trial_duration_days,
                renewal_price=price_analysis.renewal_price,
                billing_period=price_analysis.billing_period,
                currency=price_analysis.currency or (price_analysis.displayed_price.currency if price_analysis.displayed_price else None),
                previous_price=price_analysis.previous_price,
                current_price=price_analysis.current_price,
                price_change=price_analysis.price_change,
                price_change_percentage=price_analysis.price_change_percentage,
            )

        consumer_consequence: Optional[ConsumerConsequence] = None
        if price_analysis and not all_auxiliary:
            add_amt = price_analysis.additional_cost if price_analysis.additional_cost is not None else price_analysis.additional_costs
            # Free trial converted to recurring charge
            if price_analysis.trial_price == 0.0 and price_analysis.renewal_price:
                dur = price_analysis.trial_duration_days or "the trial"
                consumer_consequence = ConsumerConsequence(
                    type="recurring_charge",
                    amount=price_analysis.renewal_price,
                    currency=price_analysis.renewal_currency,
                    period=price_analysis.billing_period,
                    description=f"The free trial becomes a recurring {price_analysis.renewal_currency or ''}{price_analysis.renewal_price}/{price_analysis.billing_period or 'period'} charge after {dur} days.",
                )
            # Displayed price followed by late fee
            elif price_analysis.displayed_price and (price_analysis.late_disclosed or price_analysis.late_disclosure_detected) and add_amt:
                curr = price_analysis.displayed_price.currency
                base = price_analysis.displayed_price.amount
                if price_analysis.known_total is not None:
                    description = f"The initially stated {curr} {base} price is followed by an additional {curr} {add_amt} fee, bringing the known total to {curr} {price_analysis.known_total}."
                else:
                    description = f"The initially stated {curr} {base} price is followed by an additional {curr} {add_amt} fee."
                consumer_consequence = ConsumerConsequence(
                    type="additional_fee",
                    amount=add_amt,
                    currency=curr,
                    description=description,
                )
            # Explicit price change
            elif not price_analysis.is_alternative_pricing and (price_analysis.price_change_detected or price_analysis.price_changed or price_analysis.price_change is not None) and price_analysis.price_change is not None:
                p_diff = price_analysis.price_change
                pct = price_analysis.price_change_percentage
                sign = "+" if p_diff > 0 else ""
                consumer_consequence = ConsumerConsequence(
                    type="price_change",
                    amount=p_diff,
                    currency=price_analysis.current_currency or price_analysis.currency,
                    description=f"Price changed from {price_analysis.previous_price} to {price_analysis.current_price} ({sign}{pct}%).",
                )

        if not consumer_consequence and text_prediction and text_prediction.consumer_consequence:
            consumer_consequence = ConsumerConsequence(
                type="text_consequence",
                description=text_prediction.consumer_consequence,
            )

        # 10. Financial Signal vs Dark Pattern Discrimination
        is_financial_signal = bool(
            price_analysis and (
                price_analysis.price_change_detected
                or price_analysis.late_disclosed
                or price_analysis.late_disclosure_detected
                or price_analysis.additional_costs is not None
                or price_analysis.additional_cost is not None
                or price_analysis.additional_cost_detected
                or price_analysis.recurring
                or price_analysis.trial_price is not None
                or price_analysis.renewal_price is not None
                or price_analysis.renewal_price_detected
                or price_analysis.displayed_price is not None
                or price_analysis.explicit_total is not None
                or (price_analysis.entities and len(price_analysis.entities) > 0)
            )
        )

        potential_pattern: Optional[str] = None
        dark_pattern: Optional[str] = None

        # Determine primary pattern using Preferred Order:
        # 1. Corroborated dark-pattern group
        # 2. Strong confirmed Text Predictor pattern
        # 3. Strong non-text evidence (DOM / Behavior)
        # 4. Context-required text pattern
        # 5. Financial-only pattern
        # 6. No strong signal
        corroborated_groups = [g for g in evidence_groups if g.corroborated]
        if corroborated_groups:
            potential_pattern = corroborated_groups[0].pattern
            dark_pattern = potential_pattern
        elif text_items and not text_requires_context:
            text_pat = text_items[0].pattern
            # If text pattern is generic on a pure financial fact, do not elevate to dark pattern
            if has_p_change and text_pat in (None, "potential_dark_pattern", "price_change", "other"):
                potential_pattern = "price_change"
                dark_pattern = None
            elif (has_add_cost or has_late_disc) and text_pat in (None, "potential_dark_pattern", "other") and not has_text_drip:
                potential_pattern = "price_disclosure_risk"
                dark_pattern = None
            elif (has_renewal or has_free_trial) and text_pat in (None, "potential_dark_pattern", "other") and not has_text_sub:
                potential_pattern = "subscription_risk"
                dark_pattern = None
            else:
                potential_pattern = text_pat
                dark_pattern = text_pat
        elif has_strong_non_text or has_non_text_corrob:
            strong_candidates = [
                e for e in (dom_items + beh_items)
                if e.strength == "strong" and e.pattern not in (None, "dom_signal", "behavior_signal")
            ]
            if strong_candidates:
                dark_pattern = strong_candidates[0].pattern
                potential_pattern = dark_pattern
            elif text_items and text_requires_context:
                potential_pattern = text_items[0].pattern
                dark_pattern = None
            else:
                dark_pattern = None
                potential_pattern = None
        elif text_items and text_requires_context:
            potential_pattern = text_items[0].pattern
            dark_pattern = None
        elif any(g.pattern == "drip_pricing" for g in evidence_groups) or has_add_cost or has_late_disc:
            potential_pattern = "price_disclosure_risk"
            dark_pattern = None
        elif any(g.pattern in ("subscription_risk", "subscription_structure") for g in evidence_groups) or has_renewal or has_free_trial:
            potential_pattern = "subscription_risk"
            dark_pattern = None
        elif any(g.pattern == "price_change" for g in evidence_groups) or has_p_change:
            potential_pattern = "price_change"
            dark_pattern = None
        else:
            detected_non_text = [
                e for e in (dom_items + beh_items)
                if e.pattern not in (None, "dom_signal", "behavior_signal")
            ]
            if detected_non_text:
                potential_pattern = detected_non_text[0].pattern
                dark_pattern = None
            else:
                potential_pattern = None
                dark_pattern = None

        # Contradiction pattern recognition (Phase B5.3)
        if dark_pattern is None and contradictions:
            c_with_pat = next((c for c in contradictions if c.pattern), None)
            if c_with_pat:
                dark_pattern = c_with_pat.pattern
                potential_pattern = dark_pattern

        # Determine primary pattern name and consumer risk detection
        if all_auxiliary:
            risk_detected = False
            dark_pattern = None
            potential_pattern = None
            primary_pattern = None
            score = 0.0
            risk_level = "LOW"
        elif text_requires_context and not (has_strong_non_text or has_non_text_corrob or contradictions):
            risk_detected = False
        else:
            risk_detected = bool(dark_pattern is not None)

        if risk_detected and dark_pattern:
            primary_pattern = STANDARD_PATTERN_NAMES.get(dark_pattern, dark_pattern.replace("_", " ").title())
        else:
            primary_pattern = None

        # Determine price_changed and renewal_signal
        is_alt = bool(price_analysis and price_analysis.is_alternative_pricing)
        has_actual_price_change = bool(
            price_analysis
            and not is_alt
            and (
                price_analysis.price_change_detected
                or price_analysis.price_changed
                or (price_analysis.price_change is not None and price_analysis.price_change != 0.0)
            )
            and (price_analysis.price_change != 0.0 if price_analysis.price_change is not None else True)
        )
        price_changed_val = has_actual_price_change

        renewal_signal_val = bool(
            price_analysis
            and (
                price_analysis.renewal_price is not None
                or price_analysis.renewal_price_detected
                or price_analysis.recurring
                or price_analysis.trial_price is not None
            )
        ) if price_analysis else False

        # Extract structured signals
        signals = _extract_signals(
            text_prediction=text_prediction,
            price_analysis=price_analysis,
            evidence_items=evidence_items,
            is_corroborated=has_corroboration,
            raw_text=raw_text,
        )

        # Supporting evidence with DOM / Behavior traceability (Step 9)
        supporting_evidence: List[EvidenceItem] = []
        if risk_detected and dark_pattern:
            if dark_pattern == "subscription_trap":
                supporting_evidence = [
                    e for e in evidence_items
                    if e.source == "text"
                    or e.type in ("renewal_price", "free_trial", "paid_trial")
                    or (e.source in ("dom", "behavior") and (
                        e.decision_context in ("cancellation", "subscription", "membership", "renewal")
                        or e.pattern in ("subscription_trap", "obstruction")
                    ))
                ]
            elif dark_pattern == "drip_pricing":
                supporting_evidence = [
                    e for e in evidence_items
                    if e.source == "text"
                    or e.type in ("additional_cost", "late_disclosure", "displayed_price", "post_action_fee_added", "post_action_price_changed")
                    or e.pattern in ("drip_pricing", "sneaking")
                ]
            elif dark_pattern == "obstruction":
                supporting_evidence = [
                    e for e in evidence_items
                    if e.pattern == "obstruction"
                    or (e.source in ("dom", "behavior") and e.decision_context in ("cancellation", "subscription"))
                ]
            elif dark_pattern in ("forced_action", "misdirection", "sneaking", "confirm_shaming", "urgency", "scarcity", "social_proof"):
                supporting_evidence = [
                    e for e in evidence_items
                    if e.pattern == dark_pattern or e.type == dark_pattern
                ]
            else:
                supporting_evidence = [
                    e for e in evidence_items
                    if e.source == "text" or e.pattern == dark_pattern or e.type == dark_pattern
                ]
        elif price_analysis:
            if price_changed_val:
                supporting_evidence = [e for e in evidence_items if e.type == "price_change"]
            elif renewal_signal_val:
                supporting_evidence = [e for e in evidence_items if e.type in ("renewal_price", "free_trial", "paid_trial")]
            elif has_add_cost:
                supporting_evidence = [e for e in evidence_items if e.type in ("additional_cost", "late_disclosure")]

        # Source-scoped context requirements (Part 6)
        context_requirements = {
            "text": text_requires_context,
            "price": False,
            "behavior": False,
            "dom": False,
            "image": False,
        }

        return EvidenceFusionResponse(
            source="evidence_fusion",
            risk_level=risk_level,
            risk_score=score,
            confidence=confidence,
            potential_pattern=potential_pattern,
            dark_pattern=dark_pattern,
            financial_signal=is_financial_signal,
            is_corroborated=has_corroboration,
            requires_context=has_context_required,
            context_requirements=context_requirements,
            evidence_groups=evidence_groups,
            evidence=evidence_items,
            conflicts=conflicts,
            financial_impact=financial_impact,
            consumer_consequence=consumer_consequence,
            # Phase 9.1 fields
            risk_detected=risk_detected,
            primary_pattern=primary_pattern,
            signals=signals,
            supporting_evidence=supporting_evidence,
            price_changed=price_changed_val,
            renewal_signal=renewal_signal_val,
            # Phase B5.3 fields
            contradictions=contradictions,
            temporal_relationships=temporal_relationships,
            # Phase B5.5 fields
            evidence_graph=graph.to_dict(),
            # Phase B5.6 fields
            transaction_state={
                "journey_id": next((e.journey_id for e in all_input_observations if getattr(e, "journey_id", None)), None),
                "current_stage": (
                    [e.journey_stage for e in all_input_observations if getattr(e, "journey_stage", None)][-1]
                    if any(getattr(e, "journey_stage", None) for e in all_input_observations) else None
                ),
                "stages_traversed": [e.journey_stage for e in all_input_observations if getattr(e, "journey_stage", None)],
                "stage_transitions_count": sum(1 for e in graph.edges if e.relation_type == "STAGE_TRANSITION"),
            } if any(getattr(e, "journey_stage", None) for e in all_input_observations) else None,
            # Phase B5.7 fields
            intelligence_analysis=IntelligenceEngine.analyze(
                evidence_items=evidence_items,
                contradictions=contradictions,
                temporal_relationships=temporal_relationships,
                text_prediction=text_prediction,
                price_analysis=price_analysis,
                transaction_state={
                    "journey_id": next((e.journey_id for e in all_input_observations if getattr(e, "journey_id", None)), None),
                    "current_stage": (
                        [e.journey_stage for e in all_input_observations if getattr(e, "journey_stage", None)][-1]
                        if any(getattr(e, "journey_stage", None) for e in all_input_observations) else None
                    ),
                    "stages_traversed": [e.journey_stage for e in all_input_observations if getattr(e, "journey_stage", None)],
                    "stage_transitions_count": sum(1 for e in graph.edges if e.relation_type == "STAGE_TRANSITION"),
                } if any(getattr(e, "journey_stage", None) for e in all_input_observations) else None,
            ),
        )
