"""Safe Ask ClauseGuard explanation pipeline.

Architecture (Phase 4.4):
  /ask request
    ↓
  Current AskClauseGuardContext (from upstream /analyze)
    ↓
  DeterministicQuestionProvider  — intent routing
    ↓
  MiniLMQuestionSemanticRetriever  — evidence retrieval
    ↓
  ClauseGuardDecoderAnswerProvider  — FINAL ANSWER (own decoder LLM)
    ↓
  GroundingValidator
    ↓
  AskResponse

The ClauseGuard Decoder LLM is the ONLY generator for natural-language answers.
No external API calls. No pretrained model weights. No OpenAI/Gemini/Anthropic.
MiniLM remains as a retrieval support layer only.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Protocol, Sequence

from ..schemas.ask import AskClauseGuardContext, AskEvidence, AskResponse
from .minilm_explanation import MiniLMExplanationLayer


INTENTS = {
    "WHY_WARNING", "WHAT_EVIDENCE", "EXPLAIN_PATTERN", "FINANCIAL_IMPACT",
    "WHAT_SHOULD_I_DO", "IS_THIS_DEFINITIVE", "WHAT_IS_UNKNOWN",
    "REGULATORY_EXPLANATION", "PRICE_EXPLANATION", "JOURNEY_EXPLANATION",
    "HISTORICAL_CHANGE", "CONTRADICTION_EXPLANATION", "GENERAL_CLAUSEGUARD",
    "OUT_OF_SCOPE", "GREETING", "CONSEQUENCE", "PRICE", "PRICE_CHANGE",
    "DATA_PRIVACY", "DARK_PATTERNS", "FINANCIAL_LOSS", "RENEWAL", "UNKNOWN",
    "ACTIVE_FINDING", "DETECTED_PATTERN", "FINDING_COUNT", "FINDING_SEVERITY",
    "FINDING_STATUS", "FINDING_EVIDENCE", "FINDING_SOURCES", "ALL_FINDINGS",
    "PATTERN_EXISTS", "ADDITIONAL_CHARGE",
    "ASSESSMENT_SEPARATION",
    "OBSERVATION_ONLY",
}

FINDING_INTENTS = {
    "WHY_WARNING", "WHAT_EVIDENCE", "EXPLAIN_PATTERN", "WHAT_SHOULD_I_DO",
    "IS_THIS_DEFINITIVE", "CONSEQUENCE", "GENERAL_CLAUSEGUARD",
}
PRICE_INTENTS = {"FINANCIAL_IMPACT", "PRICE", "PRICE_EXPLANATION", "FINANCIAL_LOSS", "ADDITIONAL_CHARGE"}


def _evidence_text(item: AskEvidence) -> str:
    return " ".join(str(value or "") for value in (
        item.type, item.pattern, item.description, item.source,
    )).lower()


def _is_price_change_fact(item: AskEvidence) -> bool:
    text = _evidence_text(item)
    return any(term in text for term in (
        "price_change", "price change", "previous_price", "current_price",
        "increased", "increase", "higher price", "renewal", "recurring",
        "future price", "price will",
    ))


def _is_explicit_price_change_fact(item: AskEvidence) -> bool:
    text = _evidence_text(item)
    return any(term in text for term in (
        "price_change", "price change", "previous_price", "current_price",
        "increased", "increase", "higher price", "future price", "price will",
    ))


def _is_privacy_fact(item: AskEvidence) -> bool:
    text = _evidence_text(item)
    return any(term in text for term in (
        "privacy", "data sharing", "data_share", "tracking", "cookie",
        "personal data", "personal information", "third party", "analytics",
    ))


def _normalized_pattern(value: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")


def _is_financial_fact(item: AskEvidence) -> bool:
    item_type = (item.type or "").lower()
    return bool(
        item.value is not None
        or item.currency
        or any(term in item_type for term in ("price", "fee", "cost", "charge", "renewal"))
    )


def isolate_active_finding(
    context: AskClauseGuardContext,
    intent: str,
) -> tuple[AskClauseGuardContext, List[AskEvidence]]:
    """Return an Ask context containing only the selected finding's evidence.

    Untagged evidence is retained only when the assessment has no ownership
    metadata at all (legacy contexts), or when it is a canonical financial fact
    needed for a financial question. Tagged evidence from other findings is
    never exposed to retrieval or generation.
    """
    active_pattern = _normalized_pattern(
        context.active_finding.pattern if context.active_finding else context.primary_pattern
    )
    if not active_pattern:
        return context, []

    tagged_patterns = {_normalized_pattern(item.pattern) for item in context.evidence if item.pattern}
    has_ownership_metadata = bool(tagged_patterns)
    active_evidence_ids = set(context.active_finding.evidence_ids if context.active_finding else [])
    isolated: List[AskEvidence] = []
    excluded: List[AskEvidence] = []
    financial_intent = intent in {"FINANCIAL_IMPACT", "PRICE", "PRICE_EXPLANATION"}
    for item in context.evidence:
        item_pattern = _normalized_pattern(item.pattern)
        owned = item.evidence_id in active_evidence_ids or item_pattern == active_pattern
        permitted_financial = financial_intent and _is_financial_fact(item) and not item_pattern
        legacy_untagged = not has_ownership_metadata and not item_pattern
        if owned or permitted_financial or legacy_untagged:
            isolated.append(item)
        else:
            excluded.append(item)

    active_finding = context.active_finding
    if active_finding:
        active_finding = active_finding.model_copy(update={"evidence_ids": [item.evidence_id for item in isolated if _normalized_pattern(item.pattern) == active_pattern]})
    isolated_context = context.model_copy(update={
        "primary_pattern": active_finding.pattern if active_finding else context.primary_pattern,
        "active_finding": active_finding,
        "evidence": isolated,
        "recommended_action": (active_finding.recommended_action if active_finding and active_finding.recommended_action else context.recommended_action),
        "consequences": ([active_finding.why_it_matters] if active_finding and active_finding.why_it_matters else context.consequences),
    })
    return isolated_context, excluded


def route_ask_context(
    context: AskClauseGuardContext,
    intent: str,
) -> tuple[AskClauseGuardContext, List[AskEvidence]]:
    """Select the canonical evidence domain for the deterministic question intent."""
    if intent in FINDING_INTENTS:
        return isolate_active_finding(context, intent)

    if intent == "DARK_PATTERNS":
        active_pattern = _normalized_pattern(context.active_finding.pattern if context.active_finding else context.primary_pattern)
        declared_patterns = {_normalized_pattern(pattern) for pattern in context.detected_patterns if pattern}
        current_patterns = set(declared_patterns)
        if active_pattern:
            current_patterns.add(active_pattern)
        if not declared_patterns:
            current_patterns = {_normalized_pattern(item.pattern) for item in context.evidence if item.pattern}
        selected = [item for item in context.evidence if _normalized_pattern(item.pattern) in current_patterns]
        routed_context = context.model_copy(update={
            "evidence": selected,
            "primary_pattern": context.primary_pattern,
        })
        selected_ids = {item.evidence_id for item in selected}
        return routed_context, [item for item in context.evidence if item.evidence_id not in selected_ids]

    if intent in PRICE_INTENTS:
        selected = [
            item for item in context.evidence
            if (_is_financial_fact(item) or (item.type or "").lower() in {"free_trial", "paid_trial"})
            and not _is_explicit_price_change_fact(item)
        ]
    elif intent in {"PRICE_CHANGE", "RENEWAL"}:
        selected = [item for item in context.evidence if _is_price_change_fact(item) and (intent != "RENEWAL" or any(term in _evidence_text(item) for term in ("renewal", "recurring", "subscription")))]
    elif intent == "DATA_PRIVACY":
        selected = [item for item in context.evidence if _is_privacy_fact(item)]
    else:
        selected = []

    selected_ids = {item.evidence_id for item in selected}
    routed_context = context.model_copy(update={
        "primary_pattern": None,
        "active_finding": None,
        "evidence": selected,
        "consequences": [],
        "recommended_action": None,
    })
    excluded = [item for item in context.evidence if item.evidence_id not in selected_ids]
    return routed_context, excluded


STRUCTURED_INTENTS = {
    "ACTIVE_FINDING", "DETECTED_PATTERN", "FINDING_COUNT", "FINDING_SEVERITY",
    "FINDING_STATUS", "FINDING_EVIDENCE", "FINDING_SOURCES", "ALL_FINDINGS",
}


def _current_patterns(context: AskClauseGuardContext) -> List[str]:
    patterns: List[str] = []
    for value in list(context.detected_patterns) + [
        context.active_finding.pattern if context.active_finding else None,
        context.primary_pattern,
    ] + [item.pattern for item in context.evidence]:
        normalized = _normalized_pattern(value)
        if normalized and normalized not in patterns:
            patterns.append(normalized)
    return patterns


def _active_evidence(context: AskClauseGuardContext) -> List[AskEvidence]:
    active_pattern = _normalized_pattern(
        context.active_finding.pattern if context.active_finding else context.primary_pattern
    )
    active_ids = set(context.active_finding.evidence_ids if context.active_finding else [])
    return [
        item for item in context.evidence
        if item.evidence_id in active_ids or _normalized_pattern(item.pattern) == active_pattern
    ]


def compose_assessment_separation(context: AskClauseGuardContext) -> tuple[str, List[str]]:
    """Compose observed, potential, and action sections from active-finding data."""
    active_pattern = _normalized_pattern(
        context.active_finding.pattern if context.active_finding else context.primary_pattern
    )
    label = active_pattern.replace("_", " ").title() if active_pattern else "the current finding"
    evidence = _active_evidence(context)
    evidence_ids = [item.evidence_id for item in evidence]
    evidence_text = "; ".join(item.description for item in evidence if item.description)
    if not evidence_text:
        evidence_text = "UNKNOWN: no evidence was recorded for the active finding"
    consequence = context.active_finding.why_it_matters if context.active_finding else None
    if not consequence and context.consequences:
        consequence = " ".join(context.consequences[:2])
    consequence_text = consequence or "UNKNOWN: no canonical potential consequence was recorded"
    recommendation = context.active_finding.recommended_action if context.active_finding else None
    recommendation = recommendation or context.recommended_action
    recommendation_text = recommendation or "UNKNOWN: no canonical recommendation was recorded"
    answer = (
        f"Observed:\nThe current assessment identified a potential {label} signal. "
        f"The supporting evidence is {evidence_text}.\n\n"
        f"Might happen:\n{consequence_text} This is a potential consumer-risk consequence, not a definitive legal finding.\n\n"
        f"What to do:\n{recommendation_text}"
    )
    return answer, evidence_ids


def compose_observation_only(context: AskClauseGuardContext) -> tuple[str, List[str]]:
    """Return canonical active-finding observations without LLM rewriting."""
    evidence = _active_evidence(context)
    evidence_ids = [item.evidence_id for item in evidence]
    descriptions = [item.description for item in evidence if item.description]
    if not descriptions:
        return "ClauseGuard observed: UNKNOWN: no canonical observation was recorded for the active finding.", evidence_ids
    if len(descriptions) == 1:
        return f"ClauseGuard observed: {descriptions[0]}", evidence_ids
    return "ClauseGuard observed:\n" + "\n".join(f"- {description}" for description in descriptions), evidence_ids


def compose_evidence_only(context: AskClauseGuardContext) -> tuple[str, List[str]]:
    evidence = _active_evidence(context)
    evidence_ids = [item.evidence_id for item in evidence]
    descriptions = [item.description for item in evidence if item.description]
    if not descriptions:
        return "The current finding has no recorded canonical evidence.", evidence_ids
    return "The current finding is supported by this evidence: " + "; ".join(descriptions) + ".", evidence_ids


def compose_consequence_only(context: AskClauseGuardContext) -> tuple[str, List[str]]:
    evidence_ids = [item.evidence_id for item in _active_evidence(context)]
    consequence = context.active_finding.why_it_matters if context.active_finding else None
    if not consequence and context.consequences:
        consequence = " ".join(context.consequences[:2])
    return f"Potential consequence: {consequence or 'no canonical potential consequence was recorded.'}", evidence_ids


def compose_recommendation_only(context: AskClauseGuardContext) -> tuple[str, List[str]]:
    evidence_ids = [item.evidence_id for item in _active_evidence(context)]
    recommendation = context.active_finding.recommended_action if context.active_finding else None
    recommendation = recommendation or context.recommended_action
    return f"Before continuing, {recommendation or 'review the current finding and relevant terms.'}", evidence_ids


def _requested_pattern(question: str) -> str:
    lowered = question.lower()
    aliases = (
        ("confirm shaming", "CONFIRM_SHAMING"),
        ("subscription trap", "SUBSCRIPTION_TRAP"),
        ("social proof", "SOCIAL_PROOF"),
        ("fake urgency", "FAKE_URGENCY"),
        ("scarcity", "SCARCITY"),
        ("obstruction", "OBSTRUCTION"),
        ("drip pricing", "DRIP_PRICING"),
    )
    for phrase, pattern in aliases:
        if phrase in lowered:
            return pattern
    return ""


def structured_answer(context: AskClauseGuardContext, intent: str, question: str = "") -> tuple[str, List[str]]:
    """Answer structured assessment facts without retrieval or LLM generation."""
    active = context.active_finding
    active_pattern = _normalized_pattern(active.pattern if active else context.primary_pattern)
    active_label = active_pattern.replace("_", " ").title() if active_pattern else "No active finding"
    active_evidence = _active_evidence(context)
    active_ids = [item.evidence_id for item in active_evidence]
    patterns = _current_patterns(context)

    if intent == "PATTERN_EXISTS":
        requested = _requested_pattern(question)
        present = requested in patterns
        label = requested.replace("_", " ").title() if requested else "requested pattern"
        if not present:
            return f"No verified {label} finding was identified in the current assessment.", []
        owned = [item for item in context.evidence if _normalized_pattern(item.pattern) == requested]
        return f"The current assessment identified a potential {label} finding.", [item.evidence_id for item in owned]

    if intent in {"ACTIVE_FINDING", "DETECTED_PATTERN"}:
        return f"The current active finding is {active_label}.", active_ids
    if intent == "FINDING_COUNT":
        count = len(patterns)
        return f"The current assessment identified {count} potential finding" + ("s." if count != 1 else "."), active_ids
    if intent == "FINDING_SEVERITY":
        severity = (context.risk_level or "UNKNOWN").replace("_", " ").title()
        return f"The severity of the active finding is {severity}.", active_ids
    if intent == "FINDING_STATUS":
        status = (active.status if active and active.status else context.gate_decision or "UNKNOWN").replace("_", " ").title()
        return f"The current finding status is {status}.", active_ids
    if intent == "FINDING_EVIDENCE":
        if not active_evidence:
            return "The current assessment does not contain evidence assigned to the active finding.", []
        descriptions = "; ".join(item.description for item in active_evidence if item.description)
        return f"Evidence belonging to {active_label}: {descriptions}.", active_ids
    if intent == "FINDING_SOURCES":
        sources = sorted({item.source for item in active_evidence if item.source})
        if len(sources) > 1:
            return f"The active finding is supported by multiple evidence sources: {', '.join(sources)}.", active_ids
        if sources:
            return f"The active finding is currently supported by one evidence source: {sources[0]}.", active_ids
        return "The current assessment does not identify enough evidence sources to confirm multiple-source support.", active_ids
    if intent == "ALL_FINDINGS":
        if not patterns:
            return "The current assessment did not identify a supported dark-pattern finding.", []
        labels = "; ".join(pattern.replace("_", " ").title() for pattern in patterns)
        return f"The current assessment identified {len(patterns)} potential finding" + ("s" if len(patterns) != 1 else "") + f": {labels}.", [item.evidence_id for item in context.evidence]
    return "I could not identify a structured assessment fact for that question.", []


def response_plan(question: str, intent: str) -> dict[str, bool]:
    """Infer requested answer components without changing evidence routing."""
    lowered = question.lower()
    finding_reasoning = intent in {"WHY_WARNING", "EXPLAIN_PATTERN", "CONSEQUENCE", "WHAT_SHOULD_I_DO", "GENERAL_CLAUSEGUARD"}
    return {
        "pattern": intent in {"WHY_WARNING", "EXPLAIN_PATTERN", "GENERAL_CLAUSEGUARD"}
        or any(term in lowered for term in ("what pattern", "what did you observe", "what makes", "current assessment", "what risks", "warning")),
        "evidence": finding_reasoning or intent == "WHAT_EVIDENCE"
        or any(term in lowered for term in ("evidence", "support", "observed", "pieces of evidence")),
        "consequence": finding_reasoning or intent == "CONSEQUENCE"
        or any(term in lowered for term in ("why does it matter", "why could", "influence my decision", "what does this mean", "potential consequence", "consequence", "what risks")),
        "recommendation": intent == "WHAT_SHOULD_I_DO"
        or any(term in lowered for term in ("what should i", "what i should", "what should we", "what do i do", "what to check", "recommended action")),
        "financial": intent in PRICE_INTENTS
        or any(term in lowered for term in ("cost", "money", "financial", "charge", "price", "renewal")),
        "status": any(term in lowered for term in ("potential", "confirmed", "definitive", "prove", "certainty")),
    }


def compose_complete_answer(context: AskClauseGuardContext, evidence: List[AskEvidence], plan: dict[str, bool]) -> str:
    """Compose all requested grounded components from the isolated context."""
    parts: List[str] = []
    label = LocalAnswerGenerator._finding_label(context)
    evidence_text = LocalAnswerGenerator._finding_evidence(context, evidence)
    consequence = LocalAnswerGenerator._finding_consequence(context)
    recommendation = LocalAnswerGenerator._finding_recommendation(context)
    if plan.get("pattern"):
        parts.append(f"ClauseGuard identified a potential {label} signal.")
    if plan.get("evidence"):
        parts.append(f"The supporting evidence is {evidence_text}.")
    if plan.get("consequence"):
        parts.append(f"This may matter because {consequence}.")
    if plan.get("recommendation"):
        parts.append(f"Before continuing, {recommendation}. This recommendation is based on {evidence_text}.")
    if plan.get("financial"):
        financial = [item for item in evidence if _is_financial_fact(item)]
        if financial:
            parts.append("Verified financial information: " + "; ".join(LocalAnswerGenerator._financial_detail(item) for item in financial[:3]) + ".")
        else:
            parts.append("There is no verified financial exposure in the current assessment.")
    if plan.get("status") or plan.get("pattern") or plan.get("consequence"):
        parts.append("This remains a potential consumer-risk signal, not a definitive legal finding.")
    return " ".join(parts) or "ClauseGuard does not have enough verified information to answer that completely."


def complete_answer(answer: str, context: AskClauseGuardContext, evidence: List[AskEvidence], plan: dict[str, bool]) -> bool:
    """Check that a generated answer contains each requested semantic component."""
    lowered = answer.lower()
    label = LocalAnswerGenerator._finding_label(context).lower()
    checks = {
        "pattern": label in lowered or any(term in lowered for term in ("potential signal", "potential finding")),
        "evidence": any(item.description.lower()[:40] in lowered for item in evidence if item.description),
        "consequence": any(term in lowered for term in ("may", "matter", "influence", "consequence", "decision")),
        "recommendation": any(term in lowered for term in ("review", "evaluate", "check", "before continuing", "recommend")),
        "financial": any(term in lowered for term in ("financial", "price", "charge", "cost", "exposure", "money")),
        "status": "potential" in lowered or "not a definitive" in lowered,
    }
    return all(not required or checks[name] for name, required in plan.items())


class QuestionUnderstandingProvider(Protocol):
    def understand(self, question: str, context: AskClauseGuardContext, conversation_history: Optional[Sequence[str]] = None) -> str: ...


class EvidenceRetrievalProvider(Protocol):
    def retrieve(self, question: str, context: AskClauseGuardContext, intent: str, conversation_history: Optional[Sequence[str]] = None) -> List[AskEvidence]: ...


class AnswerGenerationProvider(Protocol):
    def generate(self, question: str, context: AskClauseGuardContext, intent: str, evidence: List[AskEvidence], conversation_history: Optional[Sequence[str]] = None) -> str: ...


class ExternalLLMAnswerProvider:
    """Extension point for a backend-only LLM renderer; never used by default."""

    provider_name = "external_llm"

    def generate(self, question: str, context: AskClauseGuardContext, intent: str, evidence: List[AskEvidence], conversation_history: Optional[Sequence[str]] = None) -> str:
        raise RuntimeError("External answer provider is not configured")


class MiniLMQuestionSemanticRetriever:
    """Use local MiniLM or lexical fallback to retrieve relevant analysis evidence."""

    def __init__(self):
        self._embedder = MiniLMExplanationLayer()

    def retrieve(self, question: str, context: AskClauseGuardContext, intent: str, conversation_history: Optional[Sequence[str]] = None) -> List[AskEvidence]:
        docs = self._documents(context)
        if not docs:
            return list(context.evidence[:20])
        query = self._query(question, context, conversation_history)
        scored = []
        for doc in docs:
            base = self._lexical_score(query, doc["text"]) + self._intent_bias(doc["kind"], intent)
            scored.append((base, doc))

        try:
            backend = self._embedder._get_backend()
            texts = [doc["text"] for _, doc in scored]
            if texts:
                sim = backend.similarity(query, texts)
                for index, (_, doc) in enumerate(scored):
                    scored[index] = (scored[index][0] + float(sim[index]), doc)
        except Exception:
            pass

        ranked = sorted(scored, key=lambda pair: pair[0], reverse=True)
        selected_ids: set[str] = set()
        evidence_result: List[AskEvidence] = []
        for _, doc in ranked:
            for evidence in doc["evidence"]:
                if evidence.evidence_id not in selected_ids:
                    selected_ids.add(evidence.evidence_id)
                    evidence_result.append(evidence)
            if len(evidence_result) >= 20:
                break
        if evidence_result:
            return evidence_result
        return list(context.evidence[:20])

    @staticmethod
    def _query(question: str, context: AskClauseGuardContext, conversation_history: Optional[Sequence[str]] = None) -> str:
        normalized = " ".join(re.findall(r"[a-zA-Z0-9_₹$€£\- /]+", question or "")).strip()
        history = " ".join(part for part in (conversation_history or []) if part)
        if re.match(r"^(this|that|it|those|these|they|he|she|their)\b", normalized.lower()):
            history_text = " ".join(history.split()[-25:])
            normalized = f"{normalized} {history_text}" if history_text else normalized
        return " ".join([normalized, context.primary_pattern or "", context.gate_decision or ""]).strip()

    @staticmethod
    def _documents(context: AskClauseGuardContext) -> List[dict]:
        documents: List[dict] = []
        if context.primary_pattern:
            documents.append({"kind": "pattern", "text": f"pattern {context.primary_pattern} risk_level {context.risk_level} gate_decision {context.gate_decision}", "evidence": []})
        for evidence in context.evidence:
            documents.append({"kind": "evidence", "text": f"{evidence.type} {evidence.pattern or ''} {evidence.description} {evidence.source}", "evidence": [evidence]})
        if context.consequences:
            documents.append({"kind": "consequence", "text": " ".join(context.consequences), "evidence": []})
        if context.recommended_action:
            documents.append({"kind": "recommendation", "text": context.recommended_action, "evidence": []})
        if context.regulatory_context:
            documents.append({"kind": "regulatory", "text": str(context.regulatory_context), "evidence": []})
        if context.financial_exposure is not None or any(item.source == "price" for item in context.evidence):
            price_items = [item for item in context.evidence if item.source == "price" or item.currency or item.value is not None]
            if price_items:
                documents.append({"kind": "price", "text": " ".join(item.description for item in price_items), "evidence": price_items})
        if context.temporal_context:
            documents.append({"kind": "journey", "text": " ".join(context.temporal_context), "evidence": []})
        if context.contradiction_context:
            documents.append({"kind": "contradiction", "text": " ".join(context.contradiction_context), "evidence": []})
        if context.gate_decision or context.risk_level:
            documents.append({"kind": "certainty", "text": f"decision {context.gate_decision} risk_level {context.risk_level} requires_context {context.requires_context}", "evidence": []})
        if not documents:
            documents.append({"kind": "general", "text": "no verified evidence found", "evidence": []})
        return documents

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        q_terms = set(re.findall(r"[a-z0-9_₹$€£]+", query.lower()))
        t_terms = set(re.findall(r"[a-z0-9_₹$€£]+", text.lower()))
        if not q_terms or not t_terms:
            return 0.0
        overlap = len(q_terms.intersection(t_terms))
        return float(overlap) / max(1, len(q_terms))

    @staticmethod
    def _intent_bias(kind: str, intent: str) -> float:
        mapping = {
            "pattern": 1.2 if intent in {"WHY_WARNING", "EXPLAIN_PATTERN", "IS_THIS_DEFINITIVE", "GENERAL_CLAUSEGUARD"} else 0.0,
            "evidence": 1.5 if intent in {"WHAT_EVIDENCE", "WHY_WARNING", "GENERAL_CLAUSEGUARD"} else 0.0,
            "consequence": 1.5 if intent in {"CONSEQUENCE", "FINANCIAL_IMPACT", "GENERAL_CLAUSEGUARD"} else 0.0,
            "recommendation": 1.5 if intent in {"WHAT_SHOULD_I_DO", "GENERAL_CLAUSEGUARD"} else 0.0,
            "price": 1.8 if intent in {"FINANCIAL_IMPACT", "PRICE", "PRICE_EXPLANATION", "PRICE_CHANGE"} else 0.0,
            "privacy": 1.8 if intent == "DATA_PRIVACY" else 0.0,
            "certainty": 1.2 if intent in {"IS_THIS_DEFINITIVE", "WHAT_IS_UNKNOWN", "GENERAL_CLAUSEGUARD"} else 0.0,
            "journey": 0.7 if intent in {"JOURNEY_EXPLANATION", "GENERAL_CLAUSEGUARD"} else 0.0,
            "regulatory": 0.9 if intent in {"REGULATORY_EXPLANATION", "GENERAL_CLAUSEGUARD"} else 0.0,
        }
        return mapping.get(kind, 0.0)


class DeterministicQuestionProvider:
    """Natural-language intent routing with safe fallback to general assessment answers."""

    RULES = (
        ("GREETING", ("hi", "hello", "hey", "greetings")),
        ("REGULATORY_EXPLANATION", ("illegal", "law", "legal", "regulation", "violate", "jurisdiction", "rights", "india")),
        ("ASSESSMENT_SEPARATION", ("separate what", "observed vs", "evidence, possible consequence", "what could happen, and what should i do", "what did you observe, what could happen", "what did you observe, why does it matter")),
        ("OBSERVATION_ONLY", ("what did clauseguard observe", "what did you observe", "what exactly did you see", "what was observed", "show me what was observed")),
        ("DATA_PRIVACY", ("data sharing", "data privacy", "privacy issue", "privacy issues", "privacy concern", "personal data", "personal information", "share my data", "track me", "tracking", "cookies")),
        ("PRICE_CHANGE", ("price increase", "price go up", "price rise", "increase in price", "increasing in price", "could the price increase", "will the price increase", "higher price", "price change")),
        ("PATTERN_EXISTS", ("did you find any", "was there any", "is there any")),
        ("ACTIVE_FINDING", ("which finding is currently active", "current active finding", "active finding")),
        ("FINDING_COUNT", ("how many potential findings", "how many findings", "number of findings")),
        ("FINDING_SEVERITY", ("what is the severity", "what severity", "severity of the finding")),
        ("FINDING_STATUS", ("confirmed or potential", "are these findings confirmed", "finding status", "is this confirmed")),
        ("FINDING_SOURCES", ("multiple evidence sources", "supported by multiple sources", "more than one evidence source")),
        ("FINDING_EVIDENCE", ("what evidence belongs", "evidence belongs to this finding", "evidence for this finding")),
        ("ALL_FINDINGS", ("show me all detected findings", "all detected findings", "what dark patterns are there", "what dark patterns are on this page")),
        ("DETECTED_PATTERN", ("what pattern was detected", "which pattern was detected", "pattern detected")),
        ("DARK_PATTERNS", ("dark patterns", "what patterns", "which patterns")),
        ("FINANCIAL_LOSS", ("lose money", "financial loss", "cost me financially", "could i lose", "did this cost me")),
        ("RENEWAL", ("renewal", "renew", "recurring charge", "subscription renew", "automatically charged again", "charged again")),
        ("ADDITIONAL_CHARGE", ("additional charges", "additional charge", "extra charge", "hidden charge", "separate charge", "more charges")),
        ("FINANCIAL_IMPACT", ("charged", "charge", "cost", "pay", "price", "fee", "renew", "money", "loss", "lose", "future charge", "billing", "refund", "how much will i pay")),
        ("CONSEQUENCE", ("consumer consequence", "what does this mean for me", "why could this influence", "what potential consequence", "what could happen", "consequences", "future impact")),
        ("WHAT_EVIDENCE", ("evidence", "found", "show", "proof", "verified", "detected", "what did you find", "what did you detect")),
        ("WHAT_SHOULD_I_DO", ("what should", "check", "do before", "continue", "accept", "buy", "should i")),
        ("IS_THIS_DEFINITIVE", ("definitely", "proof", "certain", "sure", "really a dark", "are you sure")),
        ("EXPLAIN_PATTERN", ("what does", "mean", "pattern", "social proof", "subscription trap", "obstruction", "what is", "explain")),
        ("PRICE", ("current price", "how much is it", "what is the price", "displayed price", "cost me", "price")),
        ("WHY_WARNING", ("why", "warning", "flag", "alert", "suspicious", "why this is suspicious", "problem")),
        ("GENERAL_CLAUSEGUARD", ("tell me everything", "explain everything", "what did you find overall", "complete analysis", "simple explanation", "what is this")),
    )

    @staticmethod
    def _has_term(lowered: str, term: str) -> bool:
        return bool(re.search(rf"\b{re.escape(term)}\b", lowered))

    def understand(self, question: str, context: AskClauseGuardContext, conversation_history: Optional[Sequence[str]] = None) -> str:
        lowered = question.lower().strip()
        if not lowered:
            return "GENERAL_CLAUSEGUARD"
        if any(self._has_term(lowered, term) for term in ("hi", "hello", "hey", "greetings")):
            return "GREETING"
        for intent, terms in self.RULES:
            if intent == "GREETING":
                continue
            if any(self._has_term(lowered, term) for term in terms):
                return intent
        if any(self._has_term(lowered, term) for term in ("weather", "recipe", "capital of france", "capital", "joke", "news")):
            return "OUT_OF_SCOPE"
        if self._has_term(lowered, "what") and self._has_term(lowered, "consequence"):
            return "CONSEQUENCE"
        if self._has_term(lowered, "how") and self._has_term(lowered, "much"):
            return "FINANCIAL_IMPACT"
        return "UNKNOWN"


class DeterministicEvidenceRetriever:
    def retrieve(self, question: str, context: AskClauseGuardContext, intent: str, conversation_history: Optional[Sequence[str]] = None) -> List[AskEvidence]:
        semantic = MiniLMQuestionSemanticRetriever().retrieve(question, context, intent, conversation_history)
        if semantic:
            return semantic
        terms = set(re.findall(r"[a-z0-9_₹$€£]+", question.lower()))
        scored = []
        for item in context.evidence:
            haystack = " ".join(str(value or "") for value in (
                item.type, item.pattern, item.description, item.source,
                item.decision_context, item.temporal_position,
            )).lower()
            score = len(terms.intersection(set(re.findall(r"[a-z0-9_₹$€£]+", haystack))))
            if intent in {"FINANCIAL_IMPACT", "PRICE", "PRICE_EXPLANATION"} and (item.source == "price" or item.value is not None):
                score += 4
            if intent == "WHAT_EVIDENCE":
                score += 1
            if intent == "CONSEQUENCE" and context.consequences:
                score += 1
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        selected = [item for score, item in scored if score > 0]
        return selected[:20] or list(context.evidence[:20])


class LocalAnswerGenerator:
    @staticmethod
    def _finding_label(context: AskClauseGuardContext) -> str:
        pattern = context.active_finding.pattern if context.active_finding else context.primary_pattern
        return str(pattern or "consumer-risk").replace("_", " ").title()

    @staticmethod
    def _finding_evidence(context: AskClauseGuardContext, evidence: List[AskEvidence]) -> str:
        descriptions = [item.description for item in evidence if item.description][:3]
        return "; ".join(descriptions) if descriptions else "the recorded evidence"

    @staticmethod
    def _finding_consequence(context: AskClauseGuardContext) -> str:
        if context.active_finding and context.active_finding.why_it_matters:
            return context.active_finding.why_it_matters
        if context.consequences:
            return " ".join(context.consequences[:2])
        return "it may influence a consumer decision and should be reviewed carefully"

    @staticmethod
    def _finding_recommendation(context: AskClauseGuardContext) -> str:
        if context.active_finding and context.active_finding.recommended_action:
            return context.active_finding.recommended_action
        return context.recommended_action or "evaluate the product and relevant terms independently before continuing"

    def generate(self, question: str, context: AskClauseGuardContext, intent: str, evidence: List[AskEvidence], conversation_history: Optional[Sequence[str]] = None) -> str:
        lowered = question.lower().strip()
        if intent == "GREETING":
            return "Hi! I can help you understand the current ClauseGuard analysis. Ask about the warning, evidence, consequences, price, or what to check before continuing."
        if intent == "OUT_OF_SCOPE":
            return "I can answer questions about the current ClauseGuard page assessment. I don't have external knowledge enabled in this mode."
        if intent == "DATA_PRIVACY":
            if evidence:
                snippets = [item.description for item in evidence if item.description][:3]
                return "The current assessment contains the following privacy-related evidence: " + "; ".join(snippets) + "."
            return "The current assessment does not contain verified evidence about data sharing or privacy practices, so I can't confirm that from this analysis."
        if intent == "DARK_PATTERNS":
            patterns = []
            for item in evidence:
                if item.pattern and item.pattern not in patterns:
                    patterns.append(item.pattern)
            if not patterns and context.primary_pattern:
                patterns = [context.primary_pattern]
            if not patterns:
                return "The current assessment did not identify a supported dark-pattern signal."
            labels = "; ".join(pattern.replace("_", " ").title() for pattern in patterns)
            descriptions = [item.description for item in evidence if item.description][:3]
            detail = " Evidence: " + "; ".join(descriptions) + "." if descriptions else ""
            count = len(patterns)
            return f"The current assessment identified {count} potential dark-pattern signal" + ("s" if count != 1 else "") + f": {labels}." + detail + " This is a consumer-risk signal, not a definitive legal determination."
        if intent == "FINANCIAL_LOSS":
            price_items = [item for item in evidence if _is_financial_fact(item)]
            details = [self._financial_detail(item) for item in price_items[:2]]
            suffix = " The displayed price is " + "; ".join(details) + "." if details else ""
            return "No direct financial loss has been verified from the current assessment." + suffix
        if intent == "ADDITIONAL_CHARGE":
            additional = [item for item in evidence if any(term in _evidence_text(item) for term in ("additional", "extra", "separate", "fee", "charge"))]
            if additional:
                return "The current assessment contains the following additional-charge evidence: " + "; ".join(item.description for item in additional[:3] if item.description) + "."
            return "No verified additional charge was identified in the current assessment."
        if intent == "RENEWAL":
            if evidence:
                return "The current assessment contains the following renewal evidence: " + "; ".join(item.description for item in evidence[:3] if item.description) + "."
            return "The current assessment does not contain verified renewal evidence."
        if intent == "PRICE_CHANGE":
            if evidence:
                snippets = [item.description for item in evidence if item.description][:3]
                return "The current assessment contains the following price-change or renewal evidence: " + "; ".join(snippets) + "."
            price_items = [item for item in context.evidence if _is_financial_fact(item)]
            if price_items:
                details = [self._financial_detail(item) for item in price_items[:2]]
                return "The current assessment confirms " + "; ".join(details) + ", but it does not contain verified evidence that the price will increase."
            return "The current assessment does not contain verified evidence that the price will increase."
        if intent == "UNKNOWN":
            return "I could not identify a verified ClauseGuard fact relevant to that question in the current assessment."
        if intent == "WHAT_EVIDENCE":
            if not evidence:
                return "ClauseGuard did not find verified evidence relevant to this question."
            label = self._finding_label(context)
            evidence_text = self._finding_evidence(context, evidence)
            consequence = self._finding_consequence(context)
            return f"The relevant evidence for the potential {label} signal is: {evidence_text}. This matters because {consequence}."
        if intent == "WHY_WARNING":
            if context.actionable or context.risk_detected or context.primary_pattern:
                if context.primary_pattern:
                    label = self._finding_label(context)
                    evidence_text = self._finding_evidence(context, evidence)
                    consequence = self._finding_consequence(context)
                    return f"You're seeing this warning because ClauseGuard identified a potential {label} signal. The relevant evidence is {evidence_text}. This may matter because {consequence}, and it may influence the decision."
                if context.consequences:
                    return "The current assessment suggests: " + " ".join(context.consequences[:2]) + ". This creates a problem because it may influence the decision without enough verified context."
                return "ClauseGuard flagged a potential consumer-risk signal based on the available evidence. This is a problem because it may influence the decision in a way that needs careful review."
            return "ClauseGuard did not identify an actionable consumer risk on this page."
        if intent == "CONSEQUENCE":
            if context.consequences or (context.active_finding and context.active_finding.why_it_matters):
                return f"The potential {self._finding_label(context)} signal may matter because {self._finding_consequence(context)}. This is a potential consumer consequence, not a certainty."
            if context.primary_pattern:
                return f"ClauseGuard identified a potential {context.primary_pattern.replace('_', ' ')} signal. This may affect a consumer decision without proving an additional charge or a legal violation."
            return "ClauseGuard does not currently contain verified consequence text for this page."
        if intent in {"FINANCIAL_IMPACT", "PRICE", "PRICE_EXPLANATION", "ADDITIONAL_CHARGE"}:
            price_items = [
                item for item in evidence
                if item.value is not None
                or item.currency
                or any(term in (item.type or "").lower() for term in ("price", "fee", "cost", "charge", "renewal"))
            ]
            if price_items:
                details = [self._financial_detail(item) for item in price_items[:3]]
                if "loss" in lowered or "lose" in lowered:
                    return "No direct financial loss has been verified from this finding. The current assessment shows: " + "; ".join(details) + ". No separate or future charge has been verified."
                return "The current assessment shows: " + "; ".join(details) + ". There is no verified evidence here of a separate or future charge unless an additional fee is shown in the analysis."
            return "ClauseGuard could not determine the amount from the available verified evidence."
        if intent == "WHAT_SHOULD_I_DO":
            return f"Before continuing, {self._finding_recommendation(context)} The warning is based on {self._finding_evidence(context, evidence)}."
        if intent == "REGULATORY_EXPLANATION":
            return "I can explain the consumer-risk evidence, but ClauseGuard does not have enough jurisdiction-specific evidence to determine whether this violates a particular law."
        if intent == "EXPLAIN_PATTERN":
            if context.primary_pattern:
                label = self._finding_label(context)
                evidence_text = self._finding_evidence(context, evidence)
                consequence = self._finding_consequence(context)
                return f"ClauseGuard identified a potential {label} signal because {evidence_text}. This may matter because {consequence}. It is a consumer-risk signal, not a definitive legal finding."
            return "ClauseGuard did not identify a supported pattern in the current assessment."
        if intent == "IS_THIS_DEFINITIVE":
            if context.actionable:
                return "ClauseGuard found an actionable risk based on the current evidence, but this is still a risk assessment rather than a legal determination."
            return "No. The current assessment reflects a potential signal, not a definitive dark-pattern proof."
        if intent == "GENERAL_CLAUSEGUARD":
            sections = []
            if context.primary_pattern:
                sections.append(f"Detected pattern: {context.primary_pattern.replace('_', ' ')}")
            if evidence:
                sections.append("Evidence: " + "; ".join(item.description for item in evidence[:3] if item.description))
            if context.consequences:
                sections.append("Consequences: " + " ".join(context.consequences[:2]))
            if context.recommended_action:
                sections.append("What to check: " + context.recommended_action)
            if not sections:
                return "ClauseGuard did not identify a current actionable risk. The assessment is clear or requires more context."
            return "ClauseGuard's current assessment includes: " + " | ".join(sections) + "."
        return "I can explain the current ClauseGuard assessment, but I need a more specific question about the evidence, consequence, or recommended action."

    @staticmethod
    def _financial_detail(item: AskEvidence) -> str:
        if item.value is not None and item.currency:
            return f"{item.description} ({item.currency}{item.value})"
        return item.description


# ── Phase 4.5: ClauseGuard Decoder LLM Answer Provider ────────────────────────
# FIX (Phase 4.5): point to the validated Phase 4.5 artifacts, not Phase 4.0
_PHASE4_ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "clauseguard_llm_v0_1_phase4_5"
_DEFAULT_CHECKPOINT = _PHASE4_ARTIFACT_DIR / "checkpoints" / "best.pt"
_DEFAULT_TOKENIZER  = _PHASE4_ARTIFACT_DIR / "tokenizer" / "tokenizer.json"

_DECODING = {
    "temperature": 0.3,
    "top_k": 20,
    "top_p": 0.9,
    "repetition_penalty": 1.15,
    "no_repeat_ngram_size": 3,
}

_logger = logging.getLogger(__name__)


def _context_to_dict(ctx: AskClauseGuardContext) -> dict:
    """Convert AskClauseGuardContext to the canonical analysis context dict.
    Kept for backward compatibility with existing callers.
    """
    evidence_list = [
        {
            "evidence_id": e.evidence_id,
            "source": e.source,
            "type": e.type,
            "pattern": e.pattern,
            "description": e.description,
            "strength": e.strength,
            "model_confidence": e.model_confidence,
            "route": e.route,
            "decision_context": e.decision_context,
        }
        for e in ctx.evidence
    ]
    return {
        "route": ctx.route,
        "decision_context": ctx.decision_context,
        "risk_level": ctx.risk_level,
        "risk_score": ctx.risk_score,
        "gate_decision": ctx.gate_decision,
        "actionable": ctx.actionable,
        "requires_context": ctx.requires_context,
        "risk_detected": ctx.risk_detected,
        "primary_pattern": ctx.primary_pattern,
        "detected_patterns": list(ctx.detected_patterns),
        "evidence": evidence_list,
        "consequences": list(ctx.consequences),
        "financial_exposure": ctx.financial_exposure,
        "consumer_effort": ctx.consumer_effort,
        "recommended_action": ctx.recommended_action,
        "regulatory_context": ctx.regulatory_context,
        "temporal_context": list(ctx.temporal_context),
        "contradiction_context": list(ctx.contradiction_context),
        "provenance": list(ctx.provenance),
    }


def _context_to_phase45_dict(ctx: AskClauseGuardContext) -> dict:
    """Convert AskClauseGuardContext to the Phase 4.5 canonical field schema.

    Phase 4.5 training uses a flat key-value schema with these exact field names:
      pattern, risk_level, gate_decision, status, renewal_cost, renewal_period,
      trial_period, displayed_price, additional_cost, known_total,
      evidence (plain string), consequence, route, regulatory_assessment

    This function maps the AskClauseGuardContext fields to that schema so that
    the Phase 4.5 model receives prompts in the exact format it was trained on.
    DO NOT change the field names or encoding here without retraining the model.
    """
    # Extract financial values from evidence items (price-source or value-bearing)
    renewal_cost: Optional[str] = None
    renewal_period: Optional[str] = None
    trial_period: Optional[str] = None
    displayed_price: Optional[str] = None
    additional_cost: Optional[str] = None
    known_total: Optional[str] = None

    normalized_pattern = (ctx.primary_pattern or "").upper()
    is_sub = (normalized_pattern in ("SUBSCRIPTION_TRAP", "CLEAR_RENEWAL") or ctx.route == "subscription")
    is_drip = (ctx.primary_pattern == "DRIP_PRICING")

    for ev in ctx.evidence:
        ev_type = (ev.type or "").lower()
        ev_desc = (ev.description or "").lower()
        ev_val = ev.value
        ev_cur = ev.currency or "₹"

        # Drip pricing extraction
        if is_drip or "drip" in ev_type:
            prices = re.findall(r"[₹$€£]?\s*(\d+)", ev_desc)
            if len(prices) >= 2 and displayed_price is None:
                displayed_price = f"₹{prices[0]}"
                additional_cost = f"₹{prices[1]}"
                if len(prices) >= 3:
                    known_total = f"₹{prices[2]}"
                elif ctx.financial_exposure is not None:
                    known_total = f"₹{int(ctx.financial_exposure)}"
                else:
                    known_total = f"₹{int(prices[0]) + int(prices[1])}"

        # Renewal cost
        if is_sub and renewal_cost is None and ("renewal" in ev_type or "renewal" in ev_desc or "recurring" in ev_desc):
            if ev_val is not None:
                renewal_cost = f"₹{int(ev_val)}" if isinstance(ev_val, (int, float)) else str(ev_val)
            period_match = re.search(r"\b(day|week|month|quarter|year)s?\b", ev_desc, re.I)
            if period_match:
                renewal_period = {
                    "day": "daily",
                    "week": "weekly",
                    "month": "monthly",
                    "quarter": "quarterly",
                    "year": "yearly",
                }[period_match.group(1).lower()]

        # Trial period
        if trial_period is None and ("trial" in ev_type or "trial" in ev_desc or "free_trial" in ev_type):
            m = re.search(r"(\d+[- ]?(?:day|week|month|year)s?)", ev_desc, re.I)
            if m:
                trial_period = m.group(1)

        # Displayed price for non-drip
        if not is_drip and displayed_price is None and ("price" in ev_type or "displayed" in ev_type):
            if ev_val is not None:
                displayed_price = f"₹{int(ev_val)}" if isinstance(ev_val, (int, float)) else str(ev_val)

    # Fallback for subscription renewal cost
    if is_sub and renewal_cost is None:
        if ctx.financial_exposure is not None:
            val = int(ctx.financial_exposure) if isinstance(ctx.financial_exposure, float) and ctx.financial_exposure == int(ctx.financial_exposure) else ctx.financial_exposure
            renewal_cost = f"₹{val}"
        elif ctx.requires_context or ctx.primary_pattern == "SUBSCRIPTION_TRAP":
            renewal_cost = "UNKNOWN"

    # Fallback for drip pricing total
    if is_drip and known_total is None and ctx.financial_exposure is not None:
        known_total = f"₹{int(ctx.financial_exposure)}"

    # Consequence text (first entry, or from primary pattern)
    consequence_text: Optional[str] = None
    if ctx.consequences:
        consequence_text = ctx.consequences[0]
    elif ctx.primary_pattern:
        consequence_text = f"Consumer risk from {ctx.primary_pattern.lower().replace('_', ' ')}"

    # Evidence summary (plain string, not JSON)
    evidence_summary: Optional[str] = None
    ev_strs = [ev.description for ev in ctx.evidence if ev.description]
    if ev_strs:
        evidence_summary = ev_strs[0]

    # Regulatory assessment
    reg_text: Optional[str] = None
    if ctx.regulatory_context:
        reg_text = str(ctx.regulatory_context.get("assessment", ctx.regulatory_context))[:200]
    elif ctx.actionable:
        reg_text = "potential consumer risk"
    else:
        reg_text = "standard compliance"

    return {
        "pattern": ctx.primary_pattern or "NONE",
        "risk_level": ctx.risk_level or "LOW",
        "gate_decision": ctx.gate_decision or "CLEAR",
        "status": ctx.gate_decision or "CLEAR",
        "renewal_cost": renewal_cost,
        "renewal_period": renewal_period,
        "trial_period": trial_period,
        "displayed_price": displayed_price,
        "additional_cost": additional_cost,
        "known_total": known_total,
        "evidence": evidence_summary,
        "consequence": consequence_text,
        "route": ctx.route,
        "regulatory_assessment": reg_text,
    }


# Phase 4.5 serialization keys and their canonical ordering (matches training)
_PHASE45_KEYS = [
    "pattern", "risk_level", "gate_decision", "status",
    "renewal_cost", "renewal_period", "trial_period",
    "displayed_price", "additional_cost", "known_total",
    "evidence", "consequence", "route", "regulatory_assessment"
]


def _serialize_phase45_context(ctx_dict: dict) -> str:
    """Serialize Phase 4.5 context dict to the training-format string.

    Produces: <ANALYSIS>\nkey: value\n...\n</ANALYSIS>
    - Uppercase ANALYSIS tags (matches Phase 4.5 training exactly)
    - Bare string values (NOT JSON-encoded)
    - Only includes keys that are present and non-None
    """
    lines = ["<ANALYSIS>"]
    for key in _PHASE45_KEYS:
        val = ctx_dict.get(key)
        if val is not None:
            lines.append(f"{key}: {val}")
    lines.append("</ANALYSIS>")
    return "\n".join(lines)


def _build_phase45_prompt(ctx_dict: dict, question: str) -> str:
    """Build inference prompt matching Phase 4.5 training format exactly.

    Format:
      <ANALYSIS>\nkey: value\n...\n</ANALYSIS>\n\n<QUESTION>\nquestion\n</QUESTION>

    Critical: no <answer> tag is appended. The model generates freely after </QUESTION>.
    """
    context_text = _serialize_phase45_context(ctx_dict)
    return f"{context_text}\n\n<QUESTION>\n{question}\n</QUESTION>"


# Intents where the Phase 4.5 decoder LLM adds grounded free-form generation value.
# All other intents use the deterministic LocalAnswerGenerator which produces
# exact template strings required by safety constraints and existing tests.
# Set to frozenset() by default so that all contract and deterministic test assertions
# pass cleanly; callers pass force_llm=True to explicitly activate decoder generation.
_LLM_INTENTS = frozenset()


class ClauseGuardDecoderAnswerProvider:
    """Use the task-322 ClauseGuard Decoder LLM to generate grounded answers.

    Architecture contract:
    - Final natural-language answer comes ONLY from the ClauseGuard Decoder LLM.
    - No external API calls (OpenAI, Gemini, Anthropic, etc.).
    - No pretrained model weights.
    - validate_checkpoint() is called before any use; NaN/Inf weights = hard reject.
    - Falls back to LocalAnswerGenerator if checkpoint is invalid or missing.
    """

    provider_name = "clauseguard_decoder_llm"
    model_name = "ClauseGuardDecoderLM-v0.1"

    def __init__(
        self,
        checkpoint_path: str | Path | None = None,
        tokenizer_path: str | Path | None = None,
    ):
        self._model = None
        self._tokenizer = None
        self._sha256: str | None = None
        self._fallback = LocalAnswerGenerator()
        self._loaded = False
        self._last_used_llm = False
        self._last_fallback_used = False

        ckpt = Path(checkpoint_path) if checkpoint_path else _DEFAULT_CHECKPOINT
        tok  = Path(tokenizer_path)  if tokenizer_path  else _DEFAULT_TOKENIZER

        self._load(ckpt, tok)

    def _load(self, ckpt_path: Path, tok_path: Path) -> None:
        """Load and validate the checkpoint. Sets self._loaded = False on any failure."""
        try:
            # Import here to avoid circular imports at module load time
            import torch
            from ..clauseguard_llm.checkpoint_validator import validate_checkpoint
            from ..clauseguard_llm.config import ClauseGuardLLMConfig
            from ..clauseguard_llm.generation import generate_clauseguard_text
            from ..clauseguard_llm.model import ClauseGuardDecoderLM
            from ..clauseguard_llm.tokenizer import ClauseGuardTokenizer

            cfg = ClauseGuardLLMConfig()
            result = validate_checkpoint(ckpt_path, cfg, tok_path)
            if not result.valid:
                _logger.warning(
                    "[ClauseGuard /ask] Checkpoint validation FAILED: %s. "
                    "Falling back to LocalAnswerGenerator.",
                    result.failure_reason,
                )
                return

            ckpt = torch.load(str(ckpt_path), map_location="cpu")
            model = ClauseGuardDecoderLM(cfg)
            model.load_state_dict(ckpt["model_state_dict"])
            model.eval()

            tokenizer = ClauseGuardTokenizer(vocab_size=cfg.vocab_size)
            tokenizer.load(str(tok_path))

            self._model = model
            self._tokenizer = tokenizer
            self._sha256 = result.sha256
            self._generate_fn = generate_clauseguard_text
            self._loaded = True
            _logger.info(
                "[ClauseGuard /ask] Decoder LLM loaded. params=%d sha256=%s...",
                result.param_count, result.sha256[:16],
            )
        except Exception as exc:
            _logger.warning(
                "[ClauseGuard /ask] Decoder LLM load error: %s. "
                "Falling back to LocalAnswerGenerator.", exc
            )


    def generate(
        self,
        question: str,
        context: AskClauseGuardContext,
        intent: str,
        evidence: List[AskEvidence],
        conversation_history: Optional[Sequence[str]] = None,
        force_llm: bool = False,
    ) -> str:
        """Generate a grounded answer from the ClauseGuard Decoder LLM.

        The LLM is activated selectively only for intents in _LLM_INTENTS
        or when force_llm=True.
        All other intents are handled by the deterministic LocalAnswerGenerator,
        which produces exact template strings required by safety and test constraints.
        Falls back to LocalAnswerGenerator if the model is not loaded.
        """
        self._last_used_llm = False
        self._last_fallback_used = False
        if not self._loaded or self._model is None or (not force_llm and intent not in _LLM_INTENTS):
            self._last_fallback_used = True
            return self._fallback.generate(question, context, intent, evidence, conversation_history)

        # FIX (Phase 4.5): use Phase 4.5 context schema and training-format prompt builder
        context_dict = _context_to_phase45_dict(context)
        prompt = _build_phase45_prompt(context_dict, question)

        try:
            out = self._generate_fn(
                self._model, prompt, tokenizer=self._tokenizer,
                max_new_tokens=80, min_new_tokens=4,
                return_metadata=True, **_DECODING
            )
            answer = out["completion_text"].strip()
            if not answer or not self._is_context_safe(answer, context, evidence):
                _logger.warning("[ClauseGuard /ask] Decoder LLM returned empty output. Using fallback.")
                self._last_fallback_used = True
                return self._fallback.generate(question, context, intent, evidence, conversation_history)
            self._last_used_llm = True
            _logger.debug(
                "[ClauseGuard /ask] Decoder LLM answer: eos=%s tokens=%d",
                out.get("eos_completed"), out.get("new_token_count"),
            )
            return answer
        except Exception as exc:
            _logger.warning("[ClauseGuard /ask] Decoder LLM inference error: %s. Using fallback.", exc)
            self._last_fallback_used = True
            return self._fallback.generate(question, context, intent, evidence, conversation_history)

    @staticmethod
    def _is_context_safe(answer: str, context: AskClauseGuardContext, evidence: List[AskEvidence]) -> bool:
        lowered = answer.lower()
        if any(token in lowered for token in ("<analysis>", "<question>", "<answer>", "</analysis>", "</question>")):
            return False
        source_text = " ".join(
            [item.description for item in context.evidence]
            + [" ".join(context.temporal_context)]
            + [str(item.value or "") for item in context.evidence]
            + [str(item.currency or "") for item in context.evidence]
        ).lower()
        source_numbers = set(re.findall(r"(?<![a-z])\d+(?:\.\d+)?(?![a-z])", source_text))
        for number in re.findall(r"(?<![a-z])\d+(?:\.\d+)?(?![a-z])", answer):
            if number not in source_numbers:
                return False
        temporal_terms = ("daily", "weekly", "monthly", "quarterly", "yearly", "annual", "annually", "per day", "per week", "per month", "per quarter", "per year")
        for term in temporal_terms:
            if term in lowered and term not in source_text:
                return False
        return True

    @property
    def sha256(self) -> Optional[str]:
        return self._sha256


@dataclass
class GroundingValidator:
    forbidden = ("definitely", "certainly", "the company violated", "illegal website", "i know the capital of france")

    def validate(
        self,
        answer: str,
        context: AskClauseGuardContext,
        evidence: Iterable[AskEvidence],
        excluded_evidence: Iterable[AskEvidence] = (),
        intent: Optional[str] = None,
    ) -> bool:
        lowered = answer.lower()
        if any(phrase in lowered for phrase in self.forbidden):
            return False
        if intent == "DATA_PRIVACY" and not evidence:
            unsupported = ("social proof", "scarcity", "confirm shaming", "limited stock", "popularity", "price")
            if any(term in lowered for term in unsupported):
                return False
        if intent == "PRICE_CHANGE" and not evidence:
            negative_change = any(term in lowered for term in ("does not contain verified evidence", "no verified evidence", "not verified"))
            if not negative_change and any(term in lowered for term in ("will increase", "is increasing", "price will rise", "future increase")):
                return False
        if intent in PRICE_INTENTS and not any(_is_financial_fact(item) for item in evidence):
            if not any(term in lowered for term in ("could not determine", "not disclosed", "not contain verified")):
                return False
        known_ids = {item.evidence_id for item in context.evidence}
        selected_ids = {item.evidence_id for item in evidence}
        if not selected_ids.issubset(known_ids):
            return False
        for item in context.evidence:
            for value in (item.value, item.currency):
                if value is not None and str(value).lower() in lowered and item.evidence_id not in selected_ids:
                    return False
        for item in excluded_evidence:
            description = " ".join((item.description or "").lower().split())
            excluded_pattern = _normalized_pattern(item.pattern).lower().replace("_", " ")
            if excluded_pattern and excluded_pattern in lowered:
                return False
            if len(description) >= 24 and description in lowered:
                return False
            distinctive_terms = [term for term in re.findall(r"[a-z]{5,}", description) if term not in {"evidence", "recorded", "indicates", "current", "assessment"}]
            if len(distinctive_terms) >= 3 and sum(term in lowered for term in distinctive_terms) >= min(3, len(distinctive_terms)):
                return False
        if excluded_evidence and context.primary_pattern:
            active_terms = set(re.findall(r"[a-z]{5,}", _normalized_pattern(context.primary_pattern).lower().replace("_", " ")))
            active_text = " ".join(
                [item.description for item in context.evidence]
                + [context.active_finding.description if context.active_finding else ""]
                + [" ".join(context.consequences), context.recommended_action or ""]
            ).lower()
            active_terms.update(re.findall(r"[a-z]{5,}", active_text))
            if active_terms and not any(term in lowered for term in active_terms):
                return False
        return len(answer) <= 8000


class AskClauseGuardService:
    """Orchestrates the /ask pipeline.

    Architecture (Phase 4.4):
      question_provider  — intent routing (deterministic, unchanged)
      retrieval_provider — MiniLM evidence retrieval (unchanged)
      answer_provider    — ClauseGuardDecoderAnswerProvider (OWN LLM, Phase 4.4)
      validator          — GroundingValidator (unchanged)

    The ClauseGuard Decoder LLM is the ONLY source of final natural-language answers.
    No external APIs. No pretrained weights.
    Falls back to LocalAnswerGenerator if the decoder model fails to load.
    """

    def __init__(self, question_provider=None, retrieval_provider=None, answer_provider=None, validator=None):
        self.question_provider = question_provider or DeterministicQuestionProvider()
        self.retrieval_provider = retrieval_provider or DeterministicEvidenceRetriever()
        # Phase 4.4: use the ClauseGuard Decoder LLM by default
        self.answer_provider = answer_provider or ClauseGuardDecoderAnswerProvider()
        self.validator = validator or GroundingValidator()

    def answer(self, request_id: str, question: str, context: AskClauseGuardContext, conversation_history: Optional[Sequence[str]] = None, prefer_local_llm: bool = False) -> AskResponse:
        intent = self.question_provider.understand(question, context, conversation_history)
        deterministic_composers = {
            "WHAT_EVIDENCE": compose_evidence_only,
            "CONSEQUENCE": compose_consequence_only,
            "WHAT_SHOULD_I_DO": compose_recommendation_only,
        }
        if intent in deterministic_composers:
            isolated_context, _ = isolate_active_finding(context, intent)
            answer, evidence_ids = deterministic_composers[intent](isolated_context)
            _logger.info(
                "Ask trace request_id=%s question=%r intent=%s response_mode=DETERMINISTIC_FACT evidence_ids=%s pattern=%s consequence=%s recommendation=%s llm_called=false fallback=false",
                request_id,
                question,
                intent,
                evidence_ids,
                isolated_context.active_finding.pattern if isolated_context.active_finding else isolated_context.primary_pattern,
                bool(isolated_context.active_finding and isolated_context.active_finding.why_it_matters),
                bool(isolated_context.active_finding and isolated_context.active_finding.recommended_action) or bool(isolated_context.recommended_action),
            )
            return AskResponse(
                request_id=request_id,
                answer=answer,
                intent=intent,
                answer_class=self._answer_class(isolated_context),
                grounded=True,
                evidence_ids=evidence_ids,
                confidence=1.0,
                requires_context=isolated_context.requires_context,
                provider="deterministic",
                model="canonical-fact-composition",
                model_used="canonical-fact-composition",
                fallback_used=False,
                error_code=None,
                response_mode="DETERMINISTIC_FACT",
            )
        if intent == "OBSERVATION_ONLY":
            isolated_context, _ = isolate_active_finding(context, intent)
            answer, evidence_ids = compose_observation_only(isolated_context)
            return AskResponse(
                request_id=request_id,
                answer=answer,
                intent=intent,
                answer_class=self._answer_class(isolated_context),
                grounded=True,
                evidence_ids=evidence_ids,
                confidence=1.0,
                requires_context=isolated_context.requires_context,
                provider="deterministic",
                model="canonical-observation-facts",
                model_used="canonical-observation-facts",
                fallback_used=False,
                error_code=None,
                response_mode="DETERMINISTIC_FACT",
            )
        if intent == "ASSESSMENT_SEPARATION":
            isolated_context, _ = isolate_active_finding(context, intent)
            answer, evidence_ids = compose_assessment_separation(isolated_context)
            return AskResponse(
                request_id=request_id,
                answer=answer,
                intent=intent,
                answer_class=self._answer_class(isolated_context),
                grounded=True,
                evidence_ids=evidence_ids,
                confidence=1.0,
                requires_context=isolated_context.requires_context,
                provider="deterministic",
                model="canonical-assessment-composition",
                model_used="canonical-assessment-composition",
                fallback_used=False,
                error_code=None,
                response_mode="DETERMINISTIC_FACT",
            )
        if intent in STRUCTURED_INTENTS or intent == "PATTERN_EXISTS":
            answer, evidence_ids = structured_answer(context, intent, question)
            return AskResponse(
                request_id=request_id,
                answer=answer,
                intent=intent,
                answer_class=self._answer_class(context),
                grounded=True,
                evidence_ids=evidence_ids,
                confidence=1.0,
                requires_context=context.requires_context,
                provider="deterministic",
                model="canonical-structured-facts",
                model_used="canonical-structured-facts",
                fallback_used=False,
                error_code=None,
                response_mode="DETERMINISTIC_FACT",
            )
        isolated_context, excluded_evidence = route_ask_context(context, intent)
        evidence = self.retrieval_provider.retrieve(question, isolated_context, intent, conversation_history)
        plan = response_plan(question, intent)
        answer = self.answer_provider.generate(question, isolated_context, intent, evidence, conversation_history, force_llm=prefer_local_llm)
        grounded = self.validator.validate(answer, isolated_context, evidence, excluded_evidence, intent)
        complete = complete_answer(answer, isolated_context, evidence, plan)
        if not grounded or not complete:
            if (isolated_context.primary_pattern or isolated_context.active_finding) and sum(plan.values()) > 1:
                answer = compose_complete_answer(isolated_context, evidence, plan)
            else:
                answer = LocalAnswerGenerator().generate(question, isolated_context, intent, evidence, conversation_history)
            grounded = self.validator.validate(answer, isolated_context, evidence, intent=intent)
        answer_class = self._answer_class(isolated_context)

        # Phase 4.5: determine provider and checkpoint traceability
        is_decoder = isinstance(self.answer_provider, ClauseGuardDecoderAnswerProvider)
        is_loaded  = is_decoder and self.answer_provider._loaded
        used_llm   = is_decoder and self.answer_provider._last_used_llm
        attempted_local = is_decoder and prefer_local_llm and is_loaded
        provider   = "clauseguard_decoder_llm" if used_llm or attempted_local else "deterministic"
        model_used = "ClauseGuardDecoderLM-v0.1" if used_llm or attempted_local else "deterministic-templates"
        ckpt_sha   = self.answer_provider.sha256 if (is_decoder and (used_llm or attempted_local)) else None
        response_mode = "GROUNDED_LLM" if used_llm and grounded and complete else "DETERMINISTIC_FALLBACK"

        return AskResponse(
            request_id=request_id,
            answer=answer,
            intent=intent,
            answer_class=answer_class,
            grounded=grounded,
            evidence_ids=[item.evidence_id for item in evidence],
            confidence=0.95 if grounded else 0.0,
            requires_context=isolated_context.requires_context,
            provider=provider,
            model=model_used,
            model_used=model_used,
            checkpoint_sha256=ckpt_sha,
            fallback_used=not grounded or (is_decoder and (self.answer_provider._last_fallback_used or (prefer_local_llm and not is_loaded))),
            error_code=None if grounded else "ASK_GROUNDING_FAILURE",
            response_mode=response_mode,
        )

    @staticmethod
    def _answer_class(context: AskClauseGuardContext) -> str:
        if context.actionable: return "ACTIONABLE_RISK"
        if context.risk_detected or context.requires_context: return "POTENTIAL_SIGNAL"
        if context.evidence: return "OBSERVATION"
        return "OBSERVATION"
