"""backend/services/evidence_deduplicator.py
Phase B5.5 Deterministic Evidence Deduplicator & Cross-Source Clusterer.

Core Principle:
"Preserve observations, deduplicate underlying event identity."

Responsibilities:
1. Deterministic Semantic Identity & Fingerprinting across Text, Price, DOM, Behavior, and Image.
2. Boundary Gating (strict journey match, tab isolation, stage compatibility, auxiliary isolation).
3. Exact Deduplication (collapse identical observations to one EventNode while preserving all provenance).
4. Cross-Source Corroboration (link distinct modalities observing the same underlying transaction event).
5. Contradiction Protection (contradictory facts never merge into the same event).
6. Anti-Score Inflation (ensure single underlying events do not generate multiplicative risk scores).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..schemas.evidence import (
    CONTEXT_FAMILY_MAP,
    ContradictionItem,
    EvidenceConflict,
    EvidenceGroup,
    EvidenceItem,
)
from ..schemas.price import PriceAnalysisResponse
from .evidence_graph import (
    EvidenceGraph,
    EvidenceNode,
    EventNode,
    ClaimNode,
    REL_CORROBORATES,
    REL_SAME_EVENT,
    REL_DERIVED_FROM,
    REL_CONTRADICTS,
    REL_SUPPORTS,
    REL_PRECEDES,
    REL_FOLLOWS,
    REL_STAGE_TRANSITION,
    deterministic_id,
)
from .journey_engine import (
    STAGE_UNKNOWN,
    VALID_STAGE_TRANSITIONS,
    TRANSITION_VALID,
    TRANSITION_UNEXPECTED,
    JourneyEngine,
)

_logger = logging.getLogger("clauseguard_backend.evidence_deduplicator")


def _normalize_text_fingerprint(text: Optional[str]) -> str:
    """Normalize text deterministically for exact semantic identity comparison."""
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _normalize_currency(currency: Optional[str]) -> str:
    """Normalize currency symbols and codes."""
    if not currency:
        return ""
    c = currency.strip().upper()
    sym_map = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
    return sym_map.get(c, c)


def _get_context_family(context: Optional[str]) -> str:
    """Extract canonical context family."""
    if not context:
        return "unknown_family"
    return CONTEXT_FAMILY_MAP.get(str(context).strip().lower(), "unknown_family")


class EvidenceDeduplicator:
    """Phase B5.5 Deterministic Deduplicator and Cross-Source Event Clusterer."""

    def __init__(self) -> None:
        pass

    # -------------------------------------------------------------------------
    # 1. DETERMINISTIC IDENTITY FINGERPRINTING (Sections 7, 11, 12, 13, 14)
    # -------------------------------------------------------------------------

    def generate_observation_identity(self, item: EvidenceItem) -> str:
        """Generate a deterministic identity fingerprint for an individual observation.

        Safety:
        - NEVER includes credentials, passwords, card numbers, CVVs, or raw user inputs.
        - Preserves exact financial amounts, currency, recurrence, periods, and product identity.
        - Preserves exact DOM element references and behavior event indices.
        """
        source = (item.source or "").lower()
        jrn = item.journey_id or "__legacy_fallback__"
        stage = (item.journey_stage or STAGE_UNKNOWN).upper()
        ctx_fam = _get_context_family(item.decision_context)
        is_aux = "aux" if item.is_auxiliary else "tx"
        meta = item.metadata or {}
        prod_id = str(meta.get("product_id", "")).strip().lower()

        if source == "price":
            # Section 11: Structured price event identity
            val = item.value
            amt_str = f"{float(val):.2f}" if isinstance(val, (int, float)) else str(val or "")
            curr = _normalize_currency(item.currency or meta.get("currency"))
            recurrence = meta.get("recurrence", "recurring" if item.type == "renewal_price" else "one_time")
            period = str(meta.get("period", meta.get("billing_period", ""))).lower().strip()
            trial_days = str(meta.get("trial_duration_days", ""))
            return f"price|{jrn}|{is_aux}|{stage}|{ctx_fam}|{prod_id}|{item.type}|{amt_str}|{curr}|{recurrence}|{period}|{trial_days}"

        elif source == "dom":
            # Section 12: DOM event identity
            elem = (item.element_ref or "").strip()
            sig_type = (item.type or "").strip()
            route_base = (item.route or "").split("?")[0].rstrip("/").lower()
            temporal_pos = (item.temporal_position or "static").strip()
            return f"dom|{jrn}|{is_aux}|{stage}|{ctx_fam}|{route_base}|{elem}|{sig_type}|{temporal_pos}"

        elif source == "behavior":
            # Section 13: Behavior event identity (preserves event indices and temporal action)
            action = (item.type or "").strip()
            elem = (item.element_ref or "").strip()
            indices_str = ",".join(str(i) for i in sorted(item.event_indices)) if item.event_indices else "no_idx"
            route_base = (item.route or "").split("?")[0].rstrip("/").lower()
            return f"beh|{jrn}|{is_aux}|{stage}|{ctx_fam}|{route_base}|{elem}|{action}|{indices_str}"

        elif source == "image":
            # Section 14: Image signal identity
            sig_type = (item.type or "").strip()
            route_base = (item.route or "").split("?")[0].rstrip("/").lower()
            return f"img|{jrn}|{is_aux}|{stage}|{ctx_fam}|{route_base}|{sig_type}"

        else:
            # Text and fallback sources (Section 7, 8)
            norm_desc = _normalize_text_fingerprint(item.description or str(item.value or ""))
            pat = (item.pattern or item.type or "").strip()
            return f"text|{jrn}|{is_aux}|{stage}|{ctx_fam}|{prod_id}|{pat}|{norm_desc}"

    # -------------------------------------------------------------------------
    # 2. BOUNDARY GATING & CANDIDATE BUCKETING (Sections 5, 17, 19, 20)
    # -------------------------------------------------------------------------

    def partition_candidate_buckets(
        self,
        evidence_items: List[EvidenceItem],
    ) -> Dict[str, List[EvidenceItem]]:
        """Partition evidence items into candidate buckets before clustering.

        Enforces:
        - Strict journey isolation: items with different journey_ids are never in the same bucket.
        - Tab isolation: different tabs or journeys are strictly isolated.
        - Auxiliary isolation: auxiliary items are never in commercial transaction buckets.
        - Context family alignment.
        """
        buckets: Dict[str, List[EvidenceItem]] = {}

        for item in evidence_items:
            j_id = item.journey_id
            ctx_fam = _get_context_family(item.decision_context)
            is_aux = bool(item.is_auxiliary)

            # Tab ID isolation from provenance if present
            tab_str = "tab_none"
            if item.provenance:
                if isinstance(item.provenance, dict):
                    tab_val = item.provenance.get("tab_id")
                    if tab_val is not None:
                        tab_str = f"tab_{tab_val}"
                elif hasattr(item.provenance, "tab_id") and item.provenance.tab_id is not None:
                    tab_str = f"tab_{item.provenance.tab_id}"

            if is_aux:
                bucket_key = f"aux|{j_id or 'none'}|{tab_str}|{ctx_fam}"
            elif j_id:
                bucket_key = f"jrn|{j_id}|{tab_str}|{ctx_fam}"
            else:
                # Legacy fallback bucket when journey_id is absent
                bucket_key = f"legacy|{tab_str}|{ctx_fam}"

            buckets.setdefault(bucket_key, []).append(item)

        return buckets

    # -------------------------------------------------------------------------
    # 3. GRAPH CONSTRUCTION & CLUSTERING (Sections 6, 8, 9, 10, 18)
    # -------------------------------------------------------------------------

    def build_evidence_graph(
        self,
        evidence_items: List[EvidenceItem],
        contradictions: Optional[List[ContradictionItem]] = None,
    ) -> Tuple[EvidenceGraph, List[EvidenceItem]]:
        """Construct the deterministic evidence graph, cluster underlying events,
        and produce a deduplicated scoring evidence list to prevent score inflation.

        Returns:
            Tuple[EvidenceGraph, List[EvidenceItem]]:
            - graph: Complete deterministic graph with all observations preserved.
            - scoring_evidence: Deduplicated list containing only canonical observations
              for accurate additive scoring.
        """
        graph = EvidenceGraph()
        scoring_evidence: List[EvidenceItem] = []

        if not evidence_items:
            return graph, scoring_evidence

        # 1. Register every EvidenceItem as an EvidenceNode (Preserves observation provenance)
        for item in evidence_items:
            graph.add_evidence_node(item)

        # Build contradiction set for contradiction protection (Section 10)
        contradicted_eids: Set[Tuple[str, str]] = set()
        if contradictions:
            for c in contradictions:
                e_ids = c.evidence_ids or []
                for i in range(len(e_ids)):
                    for j in range(i + 1, len(e_ids)):
                        contradicted_eids.add((e_ids[i], e_ids[j]))
                        contradicted_eids.add((e_ids[j], e_ids[i]))

        # 2. Partition into candidate buckets respecting B5.4 boundaries
        buckets = self.partition_candidate_buckets(evidence_items)

        # 3. Process each bucket independently
        for bucket_key, bucket_items in sorted(buckets.items()):
            is_aux_bucket = bucket_key.startswith("aux|")

            # Step 3A: Exact Observation Deduplication within bucket (Section 8)
            exact_groups: Dict[str, List[EvidenceItem]] = {}
            for itm in bucket_items:
                fp = self.generate_observation_identity(itm)
                exact_groups.setdefault(fp, []).append(itm)

            # For each exact group:
            # - First is canonical observation (to prevent score inflation)
            # - Subsequent are exact duplicates linked via CORROBORATES
            canonical_bucket_items: List[EvidenceItem] = []
            for fp, group in exact_groups.items():
                canonical_item = group[0]
                canonical_bucket_items.append(canonical_item)
                scoring_evidence.append(canonical_item)

                if len(group) > 1:
                    c_node_id = f"node_{canonical_item.evidence_id}"
                    for dup_item in group[1:]:
                        d_node_id = f"node_{dup_item.evidence_id}"
                        graph.add_edge(
                            d_node_id,
                            c_node_id,
                            REL_CORROBORATES,
                            metadata={"is_exact_duplicate": True, "fingerprint": fp},
                        )

            # Step 3B: Cross-Source Event Clustering (Section 9)
            self._cluster_bucket_events(
                bucket_items=canonical_bucket_items,
                all_bucket_items=bucket_items,
                exact_groups=exact_groups,
                graph=graph,
                is_auxiliary=is_aux_bucket,
                scope_key=bucket_key,
                contradicted_eids=contradicted_eids,
            )

        # 4. Integrate Contradictions into the Graph (Section 10)
        if contradictions:
            for c in contradictions:
                e_ids = c.evidence_ids or []
                if len(e_ids) >= 2:
                    for i in range(len(e_ids)):
                        for j in range(i + 1, len(e_ids)):
                            na = f"node_{e_ids[i]}"
                            nb = f"node_{e_ids[j]}"
                            if na in graph.evidence_nodes and nb in graph.evidence_nodes:
                                graph.link_contradiction(na, nb, reason=c.reason)

        # 5. Phase B5.6: Stage Transition Linking between distinct EventNodes in the same journey
        for bucket_key, bucket_items in sorted(buckets.items()):
            if bucket_key.startswith("aux|"):
                continue
            # Collect unique EventNodes in this bucket in chronological/item order
            bucket_event_nodes: List[EventNode] = []
            seen_ev_nids: Set[str] = set()
            for itm in bucket_items:
                ev = graph.get_event_for_evidence(itm.evidence_id)
                if ev and ev.node_id not in seen_ev_nids:
                    seen_ev_nids.add(ev.node_id)
                    bucket_event_nodes.append(ev)

            if len(bucket_event_nodes) >= 2:
                for i in range(len(bucket_event_nodes)):
                    for j in range(i + 1, len(bucket_event_nodes)):
                        ev_a = bucket_event_nodes[i]
                        ev_b = bucket_event_nodes[j]
                        s_a = ev_a.journey_stage
                        s_b = ev_b.journey_stage
                        if s_a and s_b and s_a != s_b:
                            trans_class = JourneyEngine.classify_stage_transition(s_a, s_b)
                            if trans_class in (TRANSITION_VALID, TRANSITION_UNEXPECTED):
                                graph.link_stage_transition(
                                    ev_a.node_id,
                                    ev_b.node_id,
                                    metadata={
                                        "transition_class": trans_class,
                                        "stage_from": s_a,
                                        "stage_to": s_b,
                                    },
                                )

        return graph, scoring_evidence

    def _cluster_bucket_events(
        self,
        bucket_items: List[EvidenceItem],
        all_bucket_items: List[EvidenceItem],
        exact_groups: Dict[str, List[EvidenceItem]],
        graph: EvidenceGraph,
        is_auxiliary: bool,
        scope_key: str = "",
        contradicted_eids: Optional[Set[Tuple[str, str]]] = None,
    ) -> None:
        """Cluster distinct source observations that describe the same underlying event."""
        assigned_canonical_ids: Set[str] = set()
        c_eids = contradicted_eids or set()

        def attach_group_to_event(can_item: EvidenceItem, event_node: EventNode) -> None:
            fp = self.generate_observation_identity(can_item)
            for itm in exact_groups.get(fp, [can_item]):
                nid = f"node_{itm.evidence_id}"
                graph.link_observation_to_event(nid, event_node.node_id)
            assigned_canonical_ids.add(can_item.evidence_id)

        # Event Cluster 1: Subscription Commitment / Renewal Event
        sub_items = [
            e for e in bucket_items
            if e.evidence_id not in assigned_canonical_ids
            and (
                e.pattern in ("subscription_trap", "subscription")
                or "subscription" in (e.pattern or "")
                or e.type in ("renewal_price", "free_trial", "paid_trial", "subscription_trap", "subscription")
                or "subscription" in (e.type or "")
                or (e.source == "dom" and ("subscription" in (e.type or "") or e.type == "preselected_subscription"))
                or (e.source == "behavior" and "subscription" in (e.type or ""))
            )
        ]

        if sub_items:
            # Check contradiction safety: contradictory items must NEVER merge into the same event (Section 10)
            has_contradiction = False
            for i in range(len(sub_items)):
                for j in range(i + 1, len(sub_items)):
                    ea, eb = sub_items[i], sub_items[j]
                    if (ea.evidence_id, eb.evidence_id) in c_eids or (
                        (ea.type == "free_trial" and eb.type == "paid_trial")
                        or (eb.type == "free_trial" and ea.type == "paid_trial")
                    ):
                        has_contradiction = True
                        break
                if has_contradiction:
                    break

            if has_contradiction:
                # Keep contradictory items in separate EventNodes
                for item in sub_items:
                    ev = graph.add_event_node(
                        event_type=f"signal_{item.type}",
                        canonical_pattern=item.pattern or item.type,
                        canonical_context=item.decision_context,
                        journey_id=item.journey_id,
                        journey_stage=item.journey_stage,
                        attributes={"value": item.value, "amount": item.value},
                        is_auxiliary=is_auxiliary,
                        scope_key=f"{scope_key}|contra_{item.evidence_id}",
                    )
                    attach_group_to_event(item, ev)
            else:
                price_sub_items = [e for e in sub_items if e.source == "price"]
                if len(price_sub_items) > 1:
                    # Group by distinct financial identities (amount, currency, period, trial_days, product_id)
                    price_clusters: Dict[str, List[EvidenceItem]] = {}
                    for p_item in price_sub_items:
                        amt = str(p_item.value or "")
                        curr = _normalize_currency(p_item.currency or (p_item.metadata or {}).get("currency"))
                        per = str((p_item.metadata or {}).get("period", (p_item.metadata or {}).get("billing_period", ""))).lower().strip()
                        tdays = str((p_item.metadata or {}).get("trial_duration_days", ""))
                        prod = str((p_item.metadata or {}).get("product_id", "")).strip().lower()
                        p_key = f"{amt}_{curr}_{per}_{tdays}_{prod}"
                        price_clusters.setdefault(p_key, []).append(p_item)

                    for p_key, p_cluster in price_clusters.items():
                        lead_price = p_cluster[0]
                        ev = graph.add_event_node(
                            event_type="subscription_renewal",
                            canonical_pattern="subscription_trap",
                            canonical_context=lead_price.decision_context,
                            journey_id=lead_price.journey_id,
                            journey_stage=lead_price.journey_stage,
                            attributes={
                                "amount": lead_price.value,
                                "currency": lead_price.currency,
                                "period": (lead_price.metadata or {}).get("period", (lead_price.metadata or {}).get("billing_period")),
                                "trial_duration_days": (lead_price.metadata or {}).get("trial_duration_days"),
                                "product_id": (lead_price.metadata or {}).get("product_id"),
                            },
                            is_auxiliary=is_auxiliary,
                            scope_key=f"{scope_key}|sub_{p_key}",
                        )
                        for pi in p_cluster:
                            attach_group_to_event(pi, ev)
                        for non_p in sub_items:
                            if non_p.source != "price" and non_p.evidence_id not in assigned_canonical_ids:
                                attach_group_to_event(non_p, ev)
                elif not price_sub_items:
                    # Group text items by product_id and normalized text fingerprint
                    text_groups: Dict[str, List[EvidenceItem]] = {}
                    for itm in sub_items:
                        prod = str((itm.metadata or {}).get("product_id", "")).strip().lower()
                        norm_desc = _normalize_text_fingerprint(itm.description or str(itm.value or ""))
                        t_key = f"{prod}|{norm_desc}"
                        text_groups.setdefault(t_key, []).append(itm)

                    for t_key, t_cluster in text_groups.items():
                        lead = t_cluster[0]
                        ev = graph.add_event_node(
                            event_type="subscription_renewal",
                            canonical_pattern="subscription_trap",
                            canonical_context=lead.decision_context,
                            journey_id=lead.journey_id,
                            journey_stage=lead.journey_stage,
                            attributes={
                                "product_id": (lead.metadata or {}).get("product_id"),
                                "description": lead.description,
                            },
                            is_auxiliary=is_auxiliary,
                            scope_key=f"{scope_key}|sub_txt_{t_key}",
                        )
                        for item in t_cluster:
                            attach_group_to_event(item, ev)
                else:
                    lead = sub_items[0]
                    pi = price_sub_items[0]
                    attrs = {
                        "amount": pi.value,
                        "currency": pi.currency,
                        "period": (pi.metadata or {}).get("period", (pi.metadata or {}).get("billing_period")),
                        "trial_duration_days": (pi.metadata or {}).get("trial_duration_days"),
                        "product_id": (pi.metadata or {}).get("product_id"),
                    }
                    p_key = f"{pi.value}_{pi.currency}_{attrs['period']}_{attrs['trial_duration_days']}_{attrs['product_id']}"
                    ev = graph.add_event_node(
                        event_type="subscription_renewal",
                        canonical_pattern="subscription_trap",
                        canonical_context=lead.decision_context,
                        journey_id=lead.journey_id,
                        journey_stage=lead.journey_stage,
                        attributes=attrs,
                        is_auxiliary=is_auxiliary,
                        scope_key=f"{scope_key}|sub_{p_key}",
                    )
                    for item in sub_items:
                        attach_group_to_event(item, ev)

                # Link cross-source corroboration edges between distinct sources in this event
                sources_present = {e.source for e in sub_items}
                if len(sources_present) >= 2 and not is_auxiliary and not has_contradiction:
                    for i in range(len(sub_items)):
                        for j in range(i + 1, len(sub_items)):
                            if sub_items[i].source != sub_items[j].source:
                                na = f"node_{sub_items[i].evidence_id}"
                                nb = f"node_{sub_items[j].evidence_id}"
                                graph.link_corroboration(na, nb, reason="Corroborating subscription commitment")

        # Event Cluster 2: Price Disclosure / Drip Pricing / Sneaking Event
        drip_items = [
            e for e in bucket_items
            if e.evidence_id not in assigned_canonical_ids
            and (
                e.pattern in ("drip_pricing", "hidden_fee", "sneaking")
                or e.type in ("additional_cost", "late_disclosure", "post_action_fee_added", "preselected_option", "preselected_commercial_choice")
                or "drip" in (e.type or "")
            )
        ]
        if drip_items:
            dom_drip = [e for e in drip_items if e.source == "dom"]
            distinct_elems = {e.element_ref for e in dom_drip if e.element_ref}
            if len(distinct_elems) > 1:
                # Separate distinct DOM elements into their own events
                for elem in sorted(distinct_elems):
                    elem_items = [e for e in drip_items if e.element_ref == elem]
                    lead = elem_items[0]
                    ev = graph.add_event_node(
                        event_type="price_disclosure_event",
                        canonical_pattern=lead.pattern or "drip_pricing",
                        canonical_context=lead.decision_context,
                        journey_id=lead.journey_id,
                        journey_stage=lead.journey_stage,
                        attributes={"element_ref": elem},
                        is_auxiliary=is_auxiliary,
                        scope_key=f"{scope_key}|drip_{elem}",
                    )
                    for itm in elem_items:
                        attach_group_to_event(itm, ev)
            else:
                lead = drip_items[0]
                price_drip = [e for e in drip_items if e.source == "price"]
                attrs = {}
                if price_drip:
                    attrs = {
                        "additional_cost": price_drip[0].value,
                        "currency": price_drip[0].currency,
                    }
                if dom_drip and dom_drip[0].element_ref:
                    attrs["element_ref"] = dom_drip[0].element_ref

                ev = graph.add_event_node(
                    event_type="price_disclosure_event",
                    canonical_pattern=lead.pattern or "drip_pricing",
                    canonical_context=lead.decision_context,
                    journey_id=lead.journey_id,
                    journey_stage=lead.journey_stage,
                    attributes=attrs,
                    is_auxiliary=is_auxiliary,
                    scope_key=f"{scope_key}|drip_single",
                )
                for itm in drip_items:
                    attach_group_to_event(itm, ev)

            sources_present = {e.source for e in drip_items}
            if len(sources_present) >= 2 and not is_auxiliary:
                for i in range(len(drip_items)):
                    for j in range(i + 1, len(drip_items)):
                        if drip_items[i].source != drip_items[j].source:
                            na = f"node_{drip_items[i].evidence_id}"
                            nb = f"node_{drip_items[j].evidence_id}"
                            graph.link_corroboration(na, nb, reason="Corroborating hidden cost or preselection")

        # Event Cluster 3: Urgency / Scarcity / Pressure Event (including Image signals)
        urgency_items = [
            e for e in bucket_items
            if e.evidence_id not in assigned_canonical_ids
            and (
                e.pattern in ("urgency", "scarcity", "social_proof")
                or e.type in ("urgency", "scarcity", "countdown_timer", "fake_countdown_structure", "limited_time_message", "low_stock_message")
            )
        ]
        if urgency_items:
            lead = urgency_items[0]
            ev = graph.add_event_node(
                event_type="urgency_pressure_event",
                canonical_pattern=lead.pattern or "urgency",
                canonical_context=lead.decision_context,
                journey_id=lead.journey_id,
                journey_stage=lead.journey_stage,
                attributes={},
                is_auxiliary=is_auxiliary,
                scope_key=f"{scope_key}|urgency",
            )
            for itm in urgency_items:
                attach_group_to_event(itm, ev)

            sources_present = {e.source for e in urgency_items}
            if len(sources_present) >= 2 and not is_auxiliary:
                for i in range(len(urgency_items)):
                    for j in range(i + 1, len(urgency_items)):
                        if urgency_items[i].source != urgency_items[j].source:
                            na = f"node_{urgency_items[i].evidence_id}"
                            nb = f"node_{urgency_items[j].evidence_id}"
                            graph.link_corroboration(na, nb, reason="Corroborating urgency / scarcity pressure")

        # Event Cluster 4: Cancellation Obstruction / Friction Event
        obstruction_items = [
            e for e in bucket_items
            if e.evidence_id not in assigned_canonical_ids
            and (
                e.pattern in ("obstruction", "forced_action")
                or e.type in (
                    "action_visual_deemphasis", "cancel_action_visually_deemphasized",
                    "disabled_action", "cancel_action_disabled", "hidden_action",
                    "repeated_retention_interference", "required_survey", "backtracking_loop",
                    "cancellation_obstruction", "forced_action_sequence"
                )
            )
        ]
        if obstruction_items:
            obs_groups: Dict[str, List[EvidenceItem]] = {}
            for item in obstruction_items:
                grp_k = f"{item.element_ref or 'none'}_{item.temporal_position or 'none'}"
                obs_groups.setdefault(grp_k, []).append(item)

            for grp_k, grp_items in obs_groups.items():
                lead = grp_items[0]
                ev = graph.add_event_node(
                    event_type="cancellation_obstruction",
                    canonical_pattern=lead.pattern or "obstruction",
                    canonical_context=lead.decision_context,
                    journey_id=lead.journey_id,
                    journey_stage=lead.journey_stage,
                    attributes={
                        "element_ref": lead.element_ref,
                        "temporal_position": lead.temporal_position,
                    },
                    is_auxiliary=is_auxiliary,
                    scope_key=f"{scope_key}|obs_{grp_k}",
                )
                for itm in grp_items:
                    attach_group_to_event(itm, ev)

                sources_present = {e.source for e in grp_items}
                if len(sources_present) >= 2 and not is_auxiliary:
                    for i in range(len(grp_items)):
                        for j in range(i + 1, len(grp_items)):
                            if grp_items[i].source != grp_items[j].source:
                                na = f"node_{grp_items[i].evidence_id}"
                                nb = f"node_{grp_items[j].evidence_id}"
                                graph.link_corroboration(na, nb, reason="Corroborating cancellation obstruction across interfaces")

        # Remaining isolated items: Each forms its own individual EventNode
        for item in bucket_items:
            if item.evidence_id not in assigned_canonical_ids:
                meta = item.metadata or {}
                attrs = {
                    "value": item.value,
                    "element_ref": item.element_ref,
                    "amount": item.value if item.source == "price" else "",
                    "currency": item.currency or meta.get("currency", ""),
                    "period": meta.get("period", meta.get("billing_period", "")),
                    "product_id": meta.get("product_id", ""),
                    "action": item.type if item.source == "behavior" else "",
                    "event_indices": tuple(item.event_indices) if item.event_indices else (),
                    "temporal_position": item.temporal_position or "",
                }
                ev = graph.add_event_node(
                    event_type=f"signal_{item.type}",
                    canonical_pattern=item.pattern or item.type,
                    canonical_context=item.decision_context,
                    journey_id=item.journey_id,
                    journey_stage=item.journey_stage,
                    attributes=attrs,
                    is_auxiliary=is_auxiliary,
                    scope_key=f"{scope_key}|{item.evidence_id}",
                )
                attach_group_to_event(item, ev)
