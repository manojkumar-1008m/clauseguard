"""backend/services/explanation_engine.py
ClauseGuard Phase 8.7 Consumer Explanation & Action Engine.

Transforms structured multi-source evidence from Evidence Fusion into transparent,
actionable, and evidence-grounded consumer warnings and practical advice.

Core Invariants:
1. NEVER discover new risks or classify raw text independently.
2. Ground every sentence in explicit upstream evidence items.
3. Strict separation of factual financial changes from dark pattern accusations.
4. Provide practical, non-alarming action recommendations.
5. Retain stable evidence identifiers (E001, E002, ...) for auditability.
6. Support multi-finding prioritization without collapsing disparate risks.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..schemas.evidence import (
    ConsumerConsequence,
    EvidenceConflict,
    EvidenceFusionRequest,
    EvidenceFusionResponse,
    EvidenceGroup,
    EvidenceItem,
    FinancialImpact,
)
from ..schemas.explanation import (
    ConsumerExplanationFinding,
    ExplanationRequest,
    ExplanationResponse,
)
from .evidence_fusion import EvidenceFusionEngine

logger = logging.getLogger("clauseguard_backend.explanation_engine")

CURRENCY_SYMBOLS: Dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

DISCLAIMER_TEXT = "This is a consumer-risk signal, not a legal determination."


def _format_currency(amount: Optional[float], currency: Optional[str] = None) -> str:
    """Format a monetary amount deterministically with symbol or currency code."""
    if amount is None:
        return ""
    # Check if amount is an integer
    formatted_num = f"{int(amount):,}" if amount == int(amount) else f"{amount:,.2f}"
    if currency:
        curr_upper = currency.upper()
        sym = CURRENCY_SYMBOLS.get(curr_upper)
        if sym:
            return f"{sym}{formatted_num}"
        return f"{formatted_num} {curr_upper}"
    return formatted_num


class ConsumerExplanationEngine:
    """Deterministic, template-driven Consumer Explanation & Action Engine."""

    def __init__(self, fusion_engine: Optional[EvidenceFusionEngine] = None):
        self.fusion_engine = fusion_engine or EvidenceFusionEngine()

    def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        """Generate human-readable consumer explanation from fusion evidence."""
        fusion_resp: EvidenceFusionResponse

        if request.fusion_response is not None:
            fusion_resp = request.fusion_response
        elif request.fusion_request is not None:
            fusion_resp = self.fusion_engine.fuse(request.fusion_request)
        elif request.text is not None:
            fusion_resp = self.fusion_engine.fuse(EvidenceFusionRequest(text=request.text))
        else:
            fusion_resp = self.fusion_engine.fuse(EvidenceFusionRequest())

        return self.explain_fusion_response(fusion_resp)

    def explain_fusion_response(self, resp: EvidenceFusionResponse) -> ExplanationResponse:
        """Transform an EvidenceFusionResponse into an ExplanationResponse."""
        evidence_items = resp.evidence or []
        groups = resp.evidence_groups or []
        impact = resp.financial_impact
        consequence = resp.consumer_consequence
        conflicts = resp.conflicts or []
        is_context_req = resp.requires_context

        # Check for benign / no-evidence case
        has_only_benign_price = bool(
            evidence_items and all(e.type in ("displayed_price", "explicit_total") for e in evidence_items)
        )
        if (resp.risk_level == "LOW" and not resp.dark_pattern and not is_context_req):
            if (not groups and not evidence_items) or has_only_benign_price:
                return self._build_benign_response(resp)

        findings: List[ConsumerExplanationFinding] = []
        finding_counter = 1

        # 1. Process Subscription / Trial Findings
        sub_finding = self._extract_subscription_finding(resp, f"F{finding_counter:03d}")
        if sub_finding:
            findings.append(sub_finding)
            finding_counter += 1

        # 2. Process Fee / Late-Disclosure Findings
        fee_finding = self._extract_fee_finding(resp, f"F{finding_counter:03d}")
        if fee_finding:
            findings.append(fee_finding)
            finding_counter += 1

        # 3. Process Price Change Findings
        change_finding = self._extract_price_change_finding(resp, f"F{finding_counter:03d}")
        if change_finding:
            findings.append(change_finding)
            finding_counter += 1

        # 4. Process Behavioral / UI / Text Dark Pattern Findings
        ui_findings = self._extract_pattern_findings(resp, finding_counter)
        for uf in ui_findings:
            findings.append(uf)
            finding_counter += 1

        # 5. Process Conflict Findings
        if conflicts:
            conflict_finding = self._extract_conflict_finding(conflicts, resp, f"F{finding_counter:03d}")
            if conflict_finding:
                findings.append(conflict_finding)
                finding_counter += 1

        # 6. Fallback if no specific finding generated but context is required or evidence exists
        if not findings:
            if is_context_req:
                findings.append(self._build_context_required_finding(resp, f"F{finding_counter:03d}"))
            elif evidence_items:
                if has_only_benign_price and not resp.dark_pattern:
                    return self._build_benign_response(resp)
                findings.append(self._build_general_finding(resp, f"F{finding_counter:03d}"))
            else:
                return self._build_benign_response(resp)

        # Sort findings by priority (1=highest, 6=lowest)
        findings.sort(key=lambda f: f.priority)

        # Aggregate evidence IDs across all findings and all input evidence items
        all_evidence_ids = []
        for f in findings:
            for eid in f.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)
        for e in evidence_items:
            if e.evidence_id not in all_evidence_ids:
                all_evidence_ids.append(e.evidence_id)

        # Handle context-required condition
        if resp.requires_context:
            risk_status = "context_required"
            for f in findings:
                f.requires_context = True
                if not f.title.startswith("Additional context"):
                    f.title = f"Additional context needed: {f.title}"
                f.summary = f"Additional context is needed to assess this signal. {f.summary}"
                f.recommended_action = "Review the surrounding page or checkout flow."
        elif resp.dark_pattern is not None:
            risk_status = "risk_detected"
        elif resp.financial_signal:
            risk_status = "financial_notice"
        else:
            risk_status = "no_strong_signal"

        # Primary finding dictates headline fields
        primary = findings[0]

        # Aggregate evidence summary
        all_evidence_summary = []
        for f in findings:
            for item in f.evidence_summary:
                if item not in all_evidence_summary:
                    all_evidence_summary.append(item)

        disclaimer = DISCLAIMER_TEXT if risk_status != "no_strong_signal" else None

        metadata = {
            "total_findings": len(findings),
            "priority_types": [f.type for f in findings],
            "risk_level": resp.risk_level,
            "risk_score": resp.risk_score,
            "is_corroborated": resp.is_corroborated,
            "conflicts_count": len(conflicts),
        }


        return ExplanationResponse(
            source="consumer_explanation",
            risk_status=risk_status,
            title=primary.title,
            summary=primary.summary,
            evidence_summary=all_evidence_summary,
            consumer_consequence=primary.consumer_consequence,
            financial_consequence=primary.financial_consequence,
            recommended_action=primary.recommended_action,
            evidence_ids=all_evidence_ids,
            pattern=resp.potential_pattern or primary.pattern,
            requires_context=resp.requires_context,
            confidence=resp.confidence,
            disclaimer=disclaimer,
            findings=findings,
            metadata=metadata,
        )

    # ----------------------------------------------------------------------
    # Specific Finding Extractors
    # ----------------------------------------------------------------------

    def _extract_subscription_finding(
        self, resp: EvidenceFusionResponse, finding_id: str
    ) -> Optional[ConsumerExplanationFinding]:
        """Extract subscription or trial-to-renewal finding."""
        impact = resp.financial_impact
        sub_items = [
            e for e in resp.evidence
            if e.type in ("free_trial", "paid_trial", "renewal_price", "subscription_price", "recurring_price")
            or (e.pattern == "subscription_trap")
        ]

        has_sub_evidence = bool(sub_items)
        has_sub_impact = bool(
            impact and (
                impact.renewal_price is not None
                or impact.trial_price is not None
                or impact.trial_duration_days is not None
            )
        )

        if not has_sub_evidence and not has_sub_impact:
            return None

        eids = [e.evidence_id for e in sub_items]
        curr = impact.currency if impact else (sub_items[0].currency if sub_items else "INR")

        trial_price = impact.trial_price if impact else None
        renewal_price = impact.renewal_price if impact else None
        duration = impact.trial_duration_days if impact else None
        period = impact.billing_period if impact else "month"

        # Evidence bullets
        ev_summary: List[str] = []
        if duration is not None and trial_price == 0.0:
            ev_summary.append(f"{duration}-day free trial")
        elif trial_price == 0.0:
            ev_summary.append("Free trial detected")
        elif trial_price is not None:
            ev_summary.append(f"Trial price: {_format_currency(trial_price, curr)}")

        if renewal_price is not None:
            period_str = f"/{period}" if period else ""
            ev_summary.append(f"{_format_currency(renewal_price, curr)}{period_str} renewal")
            ev_summary.append(f"Recurring billing ({period or 'regular'})")

        for e in sub_items:
            if e.source == "text" and e.description not in ev_summary:
                ev_summary.append(e.description)

        # Free Trial Case
        if trial_price == 0.0:
            duration_part = f"{duration}-day " if duration else ""
            renewal_str = _format_currency(renewal_price, curr) if renewal_price is not None else "a stated amount"
            period_str = f"/{period}" if period else "/month"
            title = "Free trial with recurring renewal"
            if resp.is_corroborated:
                title = "Free trial leads to recurring subscription"

            summary = f"Your {duration_part}free trial is followed by a {renewal_str}{period_str} recurring charge."
            consequence = f"After the trial period, the subscription changes to a recurring {renewal_str} charge per {period or 'billing cycle'}."
            action = "Check the renewal terms and cancellation process before starting the trial."

            return ConsumerExplanationFinding(
                finding_id=finding_id,
                type="subscription_risk",
                title=title,
                summary=summary,
                consumer_consequence=consequence,
                financial_consequence=f"Recurring charge of {renewal_str}{period_str} starts after trial.",
                recommended_action=action,
                evidence_ids=eids,
                pattern="subscription_trap",
                priority=2,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            )

        # Paid Trial Case
        if trial_price is not None and trial_price > 0.0:
            trial_str = _format_currency(trial_price, curr)
            renewal_str = _format_currency(renewal_price, curr) if renewal_price is not None else "a higher amount"
            period_str = f"/{period}" if period else "/month"
            duration_part = f"The {duration}-day " if duration else "The "

            title = "Paid trial followed by renewal"
            summary = f"{duration_part}trial costs {trial_str} and then changes to {renewal_str}{period_str}."
            consequence = f"After the trial, the recurring price is {renewal_str}{period_str}."
            action = f"Check when the {renewal_str} renewal begins and how cancellation works."

            return ConsumerExplanationFinding(
                finding_id=finding_id,
                type="subscription_risk",
                title=title,
                summary=summary,
                consumer_consequence=consequence,
                financial_consequence=f"Initial cost {trial_str} converts to recurring {renewal_str}{period_str}.",
                recommended_action=action,
                evidence_ids=eids,
                pattern="subscription_trap",
                priority=2,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            )

        # Recurring subscription without explicit trial
        if renewal_price is not None:
            renewal_str = _format_currency(renewal_price, curr)
            period_str = f"/{period}" if period else "/month"
            title = "Recurring subscription detected"
            summary = f"The terms indicate a recurring charge of {renewal_str}{period_str}."
            consequence = f"You are committing to regular billing of {renewal_str} per {period or 'billing cycle'}."
            action = "Verify the billing schedule and cancellation policy before proceeding."

            return ConsumerExplanationFinding(
                finding_id=finding_id,
                type="subscription_risk",
                title=title,
                summary=summary,
                consumer_consequence=consequence,
                financial_consequence=f"Recurring commitment of {renewal_str}{period_str}.",
                recommended_action=action,
                evidence_ids=eids,
                pattern="subscription_trap",
                priority=2,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            )

        return None

    def _extract_fee_finding(
        self, resp: EvidenceFusionResponse, finding_id: str
    ) -> Optional[ConsumerExplanationFinding]:
        """Extract additional fee or late disclosure finding."""
        impact = resp.financial_impact
        fee_items = [
            e for e in resp.evidence
            if e.type in ("additional_fee", "additional_cost", "late_disclosure", "processing_fee", "shipping_fee", "drip_pricing")
            or (e.pattern in ("drip_pricing", "Drip Pricing"))
        ]


        has_fee_evidence = bool(fee_items)
        has_fee_impact = bool(impact and impact.additional_cost and impact.additional_cost > 0.0)

        if not has_fee_evidence and not has_fee_impact:
            return None

        eids = [e.evidence_id for e in fee_items]
        curr = impact.currency if impact else (fee_items[0].currency if fee_items else "INR")

        init_price = impact.initial_price if impact else None
        add_cost = impact.additional_cost if impact else None
        known_total = impact.known_total if impact else None

        is_late = any(e.type == "late_disclosure" or e.metadata.get("late_disclosed") is True for e in fee_items)
        if impact and getattr(resp, "financial_impact", None):
            # Check price analyzer metadata in evidence if available
            for e in resp.evidence:
                if e.metadata.get("late_disclosed") is True:
                    is_late = True

        fee_str = _format_currency(add_cost, curr) if add_cost else "an additional fee"
        base_str = _format_currency(init_price, curr) if init_price else "the initial price"
        total_str = _format_currency(known_total, curr) if known_total else "a higher amount"

        ev_summary: List[str] = []
        if init_price is not None:
            ev_summary.append(f"Initial price: {base_str}")
        if add_cost is not None:
            ev_summary.append(f"Additional fee: {fee_str}")
        if known_total is not None:
            ev_summary.append(f"Known total: {total_str}")
        if is_late:
            ev_summary.append("Fee disclosed after upfront price")

        if is_late:
            title = "Additional cost disclosed later"
            summary = f"An additional {fee_str} fee appears after the initial {base_str} price."
            if init_price and known_total:
                consequence = f"The known cost increases from {base_str} to {total_str}."
            else:
                consequence = f"The final price includes {fee_str} added after the base price."
            action = "Check the final price before confirming the purchase."
            priority = 3  # Late disclosure has higher priority than general fee

            return ConsumerExplanationFinding(
                finding_id=finding_id,
                type="late_disclosure",
                title=title,
                summary=summary,
                consumer_consequence=consequence,
                financial_consequence=f"Known total increases to {total_str}.",
                recommended_action=action,
                evidence_ids=eids,
                pattern="drip_pricing",
                priority=priority,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            )
        else:
            title = "Additional fee detected"
            summary = f"The stated {base_str} price is followed by an additional {fee_str} fee."
            consequence = f"Known total increases to {total_str}."
            action = "Review the fee breakdown before payment."
            priority = 4

            return ConsumerExplanationFinding(
                finding_id=finding_id,
                type="additional_fee",
                title=title,
                summary=summary,
                consumer_consequence=consequence,
                financial_consequence=f"Known total increases to {total_str}.",
                recommended_action=action,
                evidence_ids=eids,
                pattern="drip_pricing",
                priority=priority,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            )

    def _extract_price_change_finding(
        self, resp: EvidenceFusionResponse, finding_id: str
    ) -> Optional[ConsumerExplanationFinding]:
        """Extract explicit price change (increase or decrease) finding."""
        impact = resp.financial_impact
        change_items = [
            e for e in resp.evidence
            if e.type in ("price_increase", "price_decrease", "price_change")
        ]

        if not change_items and not (impact and impact.price_change is not None and impact.price_change != 0.0):
            return None

        eids = [e.evidence_id for e in change_items]
        curr = impact.currency if impact else (change_items[0].currency if change_items else "INR")

        prev_price = impact.previous_price if impact else None
        curr_price = impact.current_price if impact else None
        change = impact.price_change if impact else None
        pct = impact.price_change_percentage if impact else None

        prev_str = _format_currency(prev_price, curr) if prev_price is not None else "earlier price"
        curr_str = _format_currency(curr_price, curr) if curr_price is not None else "current price"

        ev_summary = []
        if prev_price is not None:
            ev_summary.append(f"Previous price: {prev_str}")
        if curr_price is not None:
            ev_summary.append(f"Current price: {curr_str}")

        if change is not None and change > 0:
            diff_str = _format_currency(change, curr)
            pct_str = f" ({pct:.2f}%)" if pct is not None else ""
            title = "Price changed"
            summary = f"The price increased from {prev_str} to {curr_str}."
            consequence = f"That is an increase of {diff_str}{pct_str}."
            action = "Verify the current price before completing the transaction."

            return ConsumerExplanationFinding(
                finding_id=finding_id,
                type="price_change",
                title=title,
                summary=summary,
                consumer_consequence=consequence,
                financial_consequence=f"Increase of {diff_str}{pct_str}.",
                recommended_action=action,
                evidence_ids=eids,
                pattern=None,
                priority=1,  # Direct financial increase has priority 1
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            )

        elif change is not None and change < 0:
            diff_str = _format_currency(abs(change), curr)
            title = "Price decreased"
            summary = f"The price decreased from {prev_str} to {curr_str}."
            consequence = f"You save {diff_str} compared with the earlier price."
            action = "Confirm the discounted price at checkout."

            return ConsumerExplanationFinding(
                finding_id=finding_id,
                type="price_change",
                title=title,
                summary=summary,
                consumer_consequence=consequence,
                financial_consequence=f"Savings of {diff_str}.",
                recommended_action=action,
                evidence_ids=eids,
                pattern=None,
                priority=5,  # Benign price drop has lower priority
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            )

        return None

    def _extract_pattern_findings(
        self, resp: EvidenceFusionResponse, start_counter: int
    ) -> List[ConsumerExplanationFinding]:
        """Extract non-financial behavioral and interface dark pattern findings."""
        findings: List[ConsumerExplanationFinding] = []
        c = start_counter

        # Look at evidence items by pattern/type
        covered_patterns = set()

        # Check DOM timers
        dom_timers = [e for e in resp.evidence if e.type == "countdown_timer"]
        urgency_items = [e for e in resp.evidence if e.pattern in ("urgency", "Urgency") or e.type == "urgency"]

        if dom_timers or urgency_items:
            eids = [e.evidence_id for e in (dom_timers + urgency_items)]
            ev_summary = [e.description for e in (dom_timers + urgency_items)]
            if dom_timers:
                title = "Urgency signal detected"
                summary = "The page uses urgency language together with a countdown element."
                action = "Check whether the offer remains available without the countdown before deciding."
            else:
                title = "Urgency signal detected"
                summary = "The page uses time-limited language to encourage prompt action."
                action = "Take time to evaluate the terms instead of rushing due to stated deadlines."

            findings.append(ConsumerExplanationFinding(
                finding_id=f"F{c:03d}",
                type="urgency",
                title=title,
                summary=summary,
                consumer_consequence="Time pressure may encourage committing before fully reviewing details.",
                financial_consequence=None,
                recommended_action=action,
                evidence_ids=eids,
                pattern="urgency",
                priority=5,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            ))
            c += 1
            covered_patterns.add("urgency")

        # Check Scarcity
        scarcity_items = [e for e in resp.evidence if e.pattern in ("scarcity", "Scarcity") or e.type == "scarcity"]
        if scarcity_items and "scarcity" not in covered_patterns:
            eids = [e.evidence_id for e in scarcity_items]
            ev_summary = [e.description for e in scarcity_items]
            findings.append(ConsumerExplanationFinding(
                finding_id=f"F{c:03d}",
                type="scarcity",
                title="Scarcity signal detected",
                summary="The page indicates that only limited stock or quantity remains.",
                consumer_consequence="Perceived scarcity may prompt a purchase before comparing options.",
                financial_consequence=None,
                recommended_action="Verify stock information before making a rushed decision.",
                evidence_ids=eids,
                pattern="scarcity",
                priority=5,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            ))
            c += 1
            covered_patterns.add("scarcity")

        # Check Social Proof
        social_items = [e for e in resp.evidence if e.pattern in ("social_proof", "Social Proof") or e.type == "social_proof"]
        if social_items and "social_proof" not in covered_patterns:
            eids = [e.evidence_id for e in social_items]
            ev_summary = [e.description for e in social_items]
            findings.append(ConsumerExplanationFinding(
                finding_id=f"F{c:03d}",
                type="social_proof",
                title="Social-proof signal detected",
                summary="The page emphasizes other users' activity to influence the purchase decision.",
                consumer_consequence="Popularity signals may create a false sense of consensus or urgency.",
                financial_consequence=None,
                recommended_action="Evaluate the product independently instead of relying only on popularity signals.",
                evidence_ids=eids,
                pattern="social_proof",
                priority=6,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            ))
            c += 1
            covered_patterns.add("social_proof")

        # Check Misdirection
        misdirection_items = [e for e in resp.evidence if e.pattern in ("misdirection", "Misdirection") or e.type == "misdirection"]
        if misdirection_items and "misdirection" not in covered_patterns:
            eids = [e.evidence_id for e in misdirection_items]
            ev_summary = [e.description for e in misdirection_items]
            findings.append(ConsumerExplanationFinding(
                finding_id=f"F{c:03d}",
                type="misdirection",
                title="Misdirection signal detected",
                summary="The page draws attention to one choice while another relevant option is less prominent.",
                consumer_consequence="Visual emphasis may guide you toward a higher-cost or less favorable option.",
                financial_consequence=None,
                recommended_action="Review all available options carefully, not just the highlighted choice.",
                evidence_ids=eids,
                pattern="misdirection",
                priority=5,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            ))
            c += 1
            covered_patterns.add("misdirection")

        # Check Obstruction
        obstruction_items = [e for e in resp.evidence if e.pattern in ("obstruction", "Obstruction") or e.type == "obstruction"]
        if obstruction_items and "obstruction" not in covered_patterns:
            eids = [e.evidence_id for e in obstruction_items]
            ev_summary = [e.description for e in obstruction_items]
            findings.append(ConsumerExplanationFinding(
                finding_id=f"F{c:03d}",
                type="obstruction",
                title="Friction in cancellation or choice detected",
                summary="The available evidence suggests that completing the desired action requires more steps than the alternative.",
                consumer_consequence="Unnecessary friction may make canceling or opting out difficult.",
                financial_consequence=None,
                recommended_action="Look for account settings, cancellation controls, or support options before committing.",
                evidence_ids=eids,
                pattern="obstruction",
                priority=5,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            ))
            c += 1
            covered_patterns.add("obstruction")

        # Check Sneaking
        sneaking_items = [e for e in resp.evidence if e.pattern in ("sneaking", "Sneaking") or e.type == "sneaking"]
        if sneaking_items and "sneaking" not in covered_patterns:
            eids = [e.evidence_id for e in sneaking_items]
            ev_summary = [e.description for e in sneaking_items]
            findings.append(ConsumerExplanationFinding(
                finding_id=f"F{c:03d}",
                type="sneaking",
                title="Preselected add-on detected",
                summary="The checkout includes an additional option that appears preselected.",
                consumer_consequence="You may be charged for unwanted extras if not deselected.",
                financial_consequence=None,
                recommended_action="Review all selected items before payment.",
                evidence_ids=eids,
                pattern="sneaking",
                priority=4,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            ))
            c += 1
            covered_patterns.add("sneaking")

        # Check Forced Action
        forced_items = [e for e in resp.evidence if e.pattern in ("forced_action", "Forced Action") or e.type == "forced_action"]
        if forced_items and "forced_action" not in covered_patterns:
            eids = [e.evidence_id for e in forced_items]
            ev_summary = [e.description for e in forced_items]
            findings.append(ConsumerExplanationFinding(
                finding_id=f"F{c:03d}",
                type="forced_action",
                title="Required step detected",
                summary="The current flow requires an additional action before continuing.",
                consumer_consequence="You may be required to share data or register an account to complete a simple task.",
                financial_consequence=None,
                recommended_action="Check whether an alternative path is available.",
                evidence_ids=eids,
                pattern="forced_action",
                priority=5,
                requires_context=resp.requires_context,
                evidence_summary=ev_summary,
            ))
            c += 1
            covered_patterns.add("forced_action")

        return findings

    def _extract_conflict_finding(
        self, conflicts: List[EvidenceConflict], resp: EvidenceFusionResponse, finding_id: str
    ) -> Optional[ConsumerExplanationFinding]:
        """Extract contradiction or conflicting terms finding."""
        if not conflicts:
            return None
        ev_summary = [c.description for c in conflicts]
        return ConsumerExplanationFinding(
            finding_id=finding_id,
            type="contradiction",
            title="Conflicting terms detected",
            summary="Different parts of the page or terms provide conflicting price or commitment details.",
            consumer_consequence="You may be subject to different terms or charges than initially indicated.",
            financial_consequence="Possible unexpected charge due to conflicting pricing terms.",
            recommended_action="Clarify contradictory terms with the provider before proceeding.",
            evidence_ids=[e.evidence_id for e in resp.evidence],
            pattern=None,
            priority=2,
            requires_context=True,
            evidence_summary=ev_summary,
        )

    def _build_context_required_finding(
        self, resp: EvidenceFusionResponse, finding_id: str
    ) -> ConsumerExplanationFinding:
        """Build finding for context-required evaluation."""
        ev_summary = [e.description for e in resp.evidence] or ["Context-dependent wording detected"]
        return ConsumerExplanationFinding(
            finding_id=finding_id,
            type="context_required",
            title="Additional context needed",
            summary="Additional context is needed to assess this signal.",
            consumer_consequence="Limited-time or conditional language was detected, but the available text is insufficient to determine whether it represents a meaningful risk.",
            financial_consequence=None,
            recommended_action="Review the surrounding page or checkout flow.",
            evidence_ids=[e.evidence_id for e in resp.evidence],
            pattern=resp.potential_pattern,
            priority=6,
            requires_context=True,
            evidence_summary=ev_summary,
        )

    def _build_general_finding(
        self, resp: EvidenceFusionResponse, finding_id: str
    ) -> ConsumerExplanationFinding:
        """Build a generic consumer-risk finding for arbitrary evidence."""
        ev_summary = [e.description for e in resp.evidence]
        return ConsumerExplanationFinding(
            finding_id=finding_id,
            type="general_consumer_risk",
            title="Consumer risk signal detected",
            summary="A potential transaction or interface risk signal was identified.",
            consumer_consequence="The wording or structure may affect transaction clarity.",
            financial_consequence=None,
            recommended_action="Review transaction terms carefully before confirming.",
            evidence_ids=[e.evidence_id for e in resp.evidence],
            pattern=resp.potential_pattern,
            priority=5,
            requires_context=resp.requires_context,
            evidence_summary=ev_summary,
        )

    def _build_benign_response(self, resp: EvidenceFusionResponse) -> ExplanationResponse:
        """Build benign / no-risk response when no significant signals exist."""
        summary_bullets = [e.description for e in resp.evidence] or ["Standard transaction terms"]
        finding = ConsumerExplanationFinding(
            finding_id="F001",
            type="no_strong_signal",
            title="No strong consumer-risk signal detected",
            summary="The available evidence does not currently indicate a strong consumer-risk pattern.",
            consumer_consequence="Standard terms without detected high-risk indicators.",
            financial_consequence=None,
            recommended_action="Proceed normally and review final checkout totals as standard practice.",
            evidence_ids=[e.evidence_id for e in resp.evidence],
            pattern=None,
            priority=6,
            requires_context=False,
            evidence_summary=summary_bullets,
        )
        return ExplanationResponse(
            source="consumer_explanation",
            risk_status="no_strong_signal",
            title="No strong consumer-risk signal detected",
            summary="The available evidence does not currently indicate a strong consumer-risk pattern.",
            evidence_summary=summary_bullets,
            consumer_consequence=None,
            financial_consequence=None,
            recommended_action="Proceed normally and review final checkout totals as standard practice.",
            evidence_ids=[e.evidence_id for e in resp.evidence],
            pattern=None,
            requires_context=False,
            confidence=resp.confidence or 0.90,
            disclaimer=None,
            findings=[finding],
            metadata={"risk_level": "LOW", "total_findings": 1},
        )
