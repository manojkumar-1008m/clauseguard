"""backend/services/evidence_graph.py
Phase B5.5 Deterministic Evidence Graph Model for ClauseGuard.

Provides a lightweight in-memory graph representation:
- Node Types: EvidenceNode, EventNode, ClaimNode
- Controlled Relationships: SUPPORTS, CORROBORATES, DERIVED_FROM, SAME_EVENT,
  CONTRADICTS, PRECEDES, FOLLOWS

Guarantees:
- Deterministic IDs and ordering (no random UUIDs for semantic identity).
- Complete provenance preservation for every node and relationship.
- Zero PII, credentials, payment data, or raw DOM stored in nodes.
- Full traceability from underlying events back to raw observations.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple, Union

from pydantic import BaseModel, Field

from ..schemas.evidence import EvidenceItem, StructuredProvenance

_logger = logging.getLogger("clauseguard_backend.evidence_graph")

# Controlled Relationship Types (Section 6 & Phase B5.6)
REL_SUPPORTS: str = "SUPPORTS"
REL_CORROBORATES: str = "CORROBORATES"
REL_DERIVED_FROM: str = "DERIVED_FROM"
REL_SAME_EVENT: str = "SAME_EVENT"
REL_CONTRADICTS: str = "CONTRADICTS"
REL_PRECEDES: str = "PRECEDES"
REL_FOLLOWS: str = "FOLLOWS"
REL_STAGE_TRANSITION: str = "STAGE_TRANSITION"

ALLOWED_RELATIONSHIPS: Set[str] = {
    REL_SUPPORTS,
    REL_CORROBORATES,
    REL_DERIVED_FROM,
    REL_SAME_EVENT,
    REL_CONTRADICTS,
    REL_PRECEDES,
    REL_FOLLOWS,
    REL_STAGE_TRANSITION,
}


def deterministic_id(prefix: str, *components: Any) -> str:
    """Generate a stable, deterministic identifier from component values."""
    raw_str = "|".join(str(c).strip() if c is not None else "" for c in components)
    h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{h}"


class EvidenceNode(BaseModel):
    """Represents an individual source observation node in the evidence graph."""
    node_id: str = Field(..., description="Deterministic node identifier")
    node_type: Literal["evidence"] = Field(default="evidence", description="Node classifier")
    evidence_id: str = Field(..., description="Originating EvidenceItem identifier")
    source: str = Field(..., description="Observation source: text, price, dom, behavior, image, etc.")
    type: str = Field(..., description="Evidence type")
    pattern: Optional[str] = Field(None, description="Standardized pattern category")
    value: Optional[Any] = Field(None, description="Extracted value")
    currency: Optional[str] = Field(None, description="Currency code")
    description: str = Field(..., description="Observation factual description")
    strength: Optional[str] = Field(None, description="Evidence strength: weak, moderate, strong, insufficient")
    journey_id: Optional[str] = Field(None, description="Interaction journey identifier")
    journey_stage: Optional[str] = Field(None, description="Interaction journey stage")
    decision_context: Optional[str] = Field(None, description="Decision domain context")
    element_ref: Optional[str] = Field(None, description="DOM element reference")
    event_indices: List[int] = Field(default_factory=list, description="Associated interaction event indices")
    route: Optional[str] = Field(None, description="Page route or URL path")
    is_auxiliary: bool = Field(default=False, description="Whether observation originates from an auxiliary context")
    provenance: Optional[Union[Dict[str, Any], str]] = Field(None, description="Structured provenance")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Sanitized metadata")

    @classmethod
    def from_evidence_item(cls, item: EvidenceItem, node_id: Optional[str] = None) -> EvidenceNode:
        """Create an EvidenceNode directly from an existing EvidenceItem."""
        nid = node_id or f"node_{item.evidence_id}"
        # Ensure provenance is clean and serializable
        prov: Any = None
        if item.provenance:
            if hasattr(item.provenance, "model_dump"):
                prov = item.provenance.model_dump()
            elif hasattr(item.provenance, "dict"):
                prov = item.provenance.dict()
            else:
                prov = item.provenance

        # Sanitize metadata to prohibit sensitive credentials/PII
        clean_meta = {}
        for k, v in (item.metadata or {}).items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ("password", "token", "secret", "cvv", "card", "pin", "auth")):
                continue
            clean_meta[k] = v

        return cls(
            node_id=nid,
            evidence_id=item.evidence_id,
            source=item.source,
            type=item.type,
            pattern=item.pattern,
            value=item.value,
            currency=item.currency,
            description=item.description,
            strength=item.strength,
            journey_id=item.journey_id,
            journey_stage=item.journey_stage,
            decision_context=item.decision_context,
            element_ref=item.element_ref,
            event_indices=list(item.event_indices or []),
            route=item.route,
            is_auxiliary=bool(item.is_auxiliary),
            provenance=prov,
            metadata=clean_meta,
        )


class EventNode(BaseModel):
    """Represents a canonical underlying consumer/interaction event."""
    node_id: str = Field(..., description="Deterministic canonical event identifier")
    node_type: Literal["event"] = Field(default="event", description="Node classifier")
    event_type: str = Field(..., description="Canonical event classification")
    canonical_pattern: Optional[str] = Field(None, description="Dominant dark pattern or risk category")
    canonical_context: Optional[str] = Field(None, description="Governing decision context")
    journey_id: Optional[str] = Field(None, description="Associated journey identifier")
    journey_stage: Optional[str] = Field(None, description="Associated journey stage")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Structured event attributes (amount, recurrence, etc.)")
    is_auxiliary: bool = Field(default=False, description="Whether event belongs to an auxiliary context")
    observation_ids: List[str] = Field(default_factory=list, description="IDs of EvidenceNodes observing this event")
    sources: List[str] = Field(default_factory=list, description="Unique sources corroborating this event")


class ClaimNode(BaseModel):
    """Represents a semantic claim made by interface text or disclosure."""
    node_id: str = Field(..., description="Deterministic claim identifier")
    node_type: Literal["claim"] = Field(default="claim", description="Node classifier")
    claim_type: str = Field(..., description="Semantic claim type: free_trial_claim, one_time_claim, etc.")
    claim_text: str = Field(..., description="Normalized claim expression")
    journey_id: Optional[str] = Field(None, description="Associated journey identifier")
    decision_context: Optional[str] = Field(None, description="Decision domain context")
    source_evidence_id: str = Field(..., description="Evidence ID originating this claim")


class GraphEdge(BaseModel):
    """Directed edge representing a controlled semantic or temporal relationship."""
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    relation_type: str = Field(..., description="Controlled relationship type")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Traceable relationship metadata")

    def __init__(self, **data: Any) -> None:
        rel = data.get("relation_type", "")
        if rel not in ALLOWED_RELATIONSHIPS:
            raise ValueError(f"Invalid relationship type '{rel}'. Must be one of {sorted(ALLOWED_RELATIONSHIPS)}")
        super().__init__(**data)


class EvidenceGraph(BaseModel):
    """Deterministic, lightweight, in-memory Evidence Graph for Phase B5.5."""
    evidence_nodes: Dict[str, EvidenceNode] = Field(default_factory=dict)
    event_nodes: Dict[str, EventNode] = Field(default_factory=dict)
    claim_nodes: Dict[str, ClaimNode] = Field(default_factory=dict)
    edges: List[GraphEdge] = Field(default_factory=list)

    def add_evidence_node(self, item: EvidenceItem, node_id: Optional[str] = None) -> EvidenceNode:
        """Add an observation node derived from an EvidenceItem."""
        enode = EvidenceNode.from_evidence_item(item, node_id=node_id)
        self.evidence_nodes[enode.node_id] = enode
        return enode

    def add_event_node(
        self,
        event_type: str,
        node_id: Optional[str] = None,
        canonical_pattern: Optional[str] = None,
        canonical_context: Optional[str] = None,
        journey_id: Optional[str] = None,
        journey_stage: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        is_auxiliary: bool = False,
        scope_key: Optional[str] = None,
    ) -> EventNode:
        """Create and register a canonical EventNode."""
        attrs = attributes or {}
        nid = node_id or deterministic_id(
            "evt",
            scope_key or "",
            journey_id,
            journey_stage,
            canonical_context,
            event_type,
            attrs.get("amount", ""),
            attrs.get("currency", ""),
            attrs.get("period", ""),
            attrs.get("product_id", ""),
            attrs.get("element_ref", ""),
            attrs.get("action", ""),
            attrs.get("event_indices", ""),
            attrs.get("temporal_position", ""),
            attrs.get("state", ""),
        )
        ev_node = EventNode(
            node_id=nid,
            event_type=event_type,
            canonical_pattern=canonical_pattern,
            canonical_context=canonical_context,
            journey_id=journey_id,
            journey_stage=journey_stage,
            attributes=attrs,
            is_auxiliary=is_auxiliary,
        )
        self.event_nodes[nid] = ev_node
        return ev_node

    def add_claim_node(
        self,
        claim_type: str,
        claim_text: str,
        source_evidence_id: str,
        node_id: Optional[str] = None,
        journey_id: Optional[str] = None,
        decision_context: Optional[str] = None,
    ) -> ClaimNode:
        """Create and register a semantic ClaimNode."""
        nid = node_id or deterministic_id("claim", journey_id, claim_type, claim_text[:64])
        c_node = ClaimNode(
            node_id=nid,
            claim_type=claim_type,
            claim_text=claim_text,
            journey_id=journey_id,
            decision_context=decision_context,
            source_evidence_id=source_evidence_id,
        )
        self.claim_nodes[nid] = c_node
        return c_node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        """Register a relationship edge between two nodes."""
        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata or {},
        )
        # Avoid duplicate identical edges
        for existing in self.edges:
            if (
                existing.source_id == edge.source_id
                and existing.target_id == edge.target_id
                and existing.relation_type == edge.relation_type
            ):
                return existing
        self.edges.append(edge)
        return edge

    def link_observation_to_event(self, evidence_node_id: str, event_node_id: str) -> None:
        """Attach an observation to a canonical event with SAME_EVENT and DERIVED_FROM edges."""
        if evidence_node_id not in self.evidence_nodes:
            raise KeyError(f"EvidenceNode '{evidence_node_id}' does not exist in graph")
        if event_node_id not in self.event_nodes:
            raise KeyError(f"EventNode '{event_node_id}' does not exist in graph")

        ev_node = self.evidence_nodes[evidence_node_id]
        event = self.event_nodes[event_node_id]

        if evidence_node_id not in event.observation_ids:
            event.observation_ids.append(evidence_node_id)
        if ev_node.source not in event.sources:
            event.sources.append(ev_node.source)
            event.sources.sort()

        self.add_edge(evidence_node_id, event_node_id, REL_SAME_EVENT)
        self.add_edge(event_node_id, evidence_node_id, REL_DERIVED_FROM)

    def link_corroboration(self, node_a_id: str, node_b_id: str, reason: Optional[str] = None) -> None:
        """Add bidirectional CORROBORATES edges between two distinct observation nodes."""
        meta = {"reason": reason} if reason else {}
        self.add_edge(node_a_id, node_b_id, REL_CORROBORATES, metadata=meta)
        self.add_edge(node_b_id, node_a_id, REL_CORROBORATES, metadata=meta)

    def link_contradiction(self, node_a_id: str, node_b_id: str, reason: str) -> None:
        """Add bidirectional CONTRADICTS edges between conflicting observation nodes."""
        meta = {"reason": reason}
        self.add_edge(node_a_id, node_b_id, REL_CONTRADICTS, metadata=meta)
        self.add_edge(node_b_id, node_a_id, REL_CONTRADICTS, metadata=meta)

    def link_stage_transition(
        self,
        event_a_id: str,
        event_b_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Link two distinct EventNodes with STAGE_TRANSITION and chronological PRECEDES/FOLLOWS.
        
        Invariant:
        - Must connect EventNode to EventNode.
        - STAGE_TRANSITION implies chronological PRECEDES, but PRECEDES alone does not imply STAGE_TRANSITION.
        - Does not independently increase consumer risk.
        """
        if event_a_id not in self.event_nodes:
            raise KeyError(f"EventNode '{event_a_id}' does not exist in graph")
        if event_b_id not in self.event_nodes:
            raise KeyError(f"EventNode '{event_b_id}' does not exist in graph")

        meta = metadata or {}
        self.add_edge(event_a_id, event_b_id, REL_STAGE_TRANSITION, metadata=meta)
        self.add_edge(event_a_id, event_b_id, REL_PRECEDES, metadata=meta)
        self.add_edge(event_b_id, event_a_id, REL_FOLLOWS, metadata=meta)

    def get_event_for_evidence(self, evidence_id: str) -> Optional[EventNode]:
        """Find the canonical EventNode associated with an evidence_id."""
        target_nid = f"node_{evidence_id}"
        for edge in self.edges:
            if edge.relation_type == REL_SAME_EVENT and edge.source_id == target_nid:
                if edge.target_id in self.event_nodes:
                    return self.event_nodes[edge.target_id]
        return None

    def get_edges_for_node(self, node_id: str) -> List[GraphEdge]:
        """Return all edges where node_id is source or target."""
        return [e for e in self.edges if e.source_id == node_id or e.target_id == node_id]

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic dictionary serialization for API payloads."""
        return {
            "evidence_nodes": {k: v.model_dump() if hasattr(v, "model_dump") else v.dict() for k, v in sorted(self.evidence_nodes.items())},
            "event_nodes": {k: v.model_dump() if hasattr(v, "model_dump") else v.dict() for k, v in sorted(self.event_nodes.items())},
            "claim_nodes": {k: v.model_dump() if hasattr(v, "model_dump") else v.dict() for k, v in sorted(self.claim_nodes.items())},
            "edges": [e.model_dump() if hasattr(e, "model_dump") else e.dict() for e in self.edges],
            "total_nodes": len(self.evidence_nodes) + len(self.event_nodes) + len(self.claim_nodes),
            "total_edges": len(self.edges),
            "canonical_events_count": len(self.event_nodes),
        }
