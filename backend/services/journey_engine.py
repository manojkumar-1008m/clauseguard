"""backend/services/journey_engine.py
Phase B5.4 Deterministic Multi-Page Interaction Boundary & Context Engine.

Distinguishes:
- Browser/Tab Session
- Consumer Interaction Journey (journey_id)
- Page Lifecycle (page_load_id)
- Individual Interaction (event_id)

Core Invariant:
session_id != journey_id != page_load_id != event_id
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from ..schemas.evidence import EvidenceItem

_logger = logging.getLogger("clauseguard_backend.journey_engine")

# Configurable inactivity timeout (Module-level, Part 9)
JOURNEY_INACTIVITY_TIMEOUT_MS: int = 15 * 60 * 1000  # 15 minutes
JOURNEY_SOFT_IDLE_TIMEOUT_MS: int = 5 * 60 * 1000   # 5 minutes

# Maximum bounded history per tab and per journey (Part 23)
MAX_ACTIVE_JOURNEYS_PER_TAB: int = 5
MAX_EVENTS_PER_JOURNEY: int = 20

# Canonical Journey Stages (Part 5)
STAGE_DISCOVERY: str = "DISCOVERY"
STAGE_PRODUCT: str = "PRODUCT"
STAGE_CART: str = "CART"
STAGE_CHECKOUT: str = "CHECKOUT"
STAGE_PAYMENT: str = "PAYMENT"
STAGE_CONFIRMATION: str = "CONFIRMATION"

STAGE_SUBSCRIPTION: str = "SUBSCRIPTION"
STAGE_CANCELLATION: str = "CANCELLATION"
STAGE_RETENTION_STEP: str = "RETENTION_STEP"
STAGE_TERMINATION: str = "TERMINATION"

STAGE_UNKNOWN: str = "UNKNOWN"

ALLOWED_STAGES: Set[str] = {
    STAGE_DISCOVERY,
    STAGE_PRODUCT,
    STAGE_CART,
    STAGE_CHECKOUT,
    STAGE_PAYMENT,
    STAGE_CONFIRMATION,
    STAGE_SUBSCRIPTION,
    STAGE_CANCELLATION,
    STAGE_RETENTION_STEP,
    STAGE_TERMINATION,
    STAGE_UNKNOWN,
}

# Canonical Journey Statuses (Part 4 & 22)
STATUS_ACTIVE: str = "ACTIVE"
STATUS_IDLE: str = "IDLE"
STATUS_SUSPENDED: str = "SUSPENDED"
STATUS_SUSPENDED_EXTERNAL_GATEWAY: str = "SUSPENDED_EXTERNAL_GATEWAY"
STATUS_COMPLETED: str = "COMPLETED"
STATUS_ABANDONED: str = "ABANDONED"
STATUS_EXPIRED_INACTIVE: str = "EXPIRED_INACTIVE"
STATUS_TERMINATED: str = "TERMINATED"

ALLOWED_STATUSES: Set[str] = {
    STATUS_ACTIVE,
    STATUS_IDLE,
    STATUS_SUSPENDED,
    STATUS_SUSPENDED_EXTERNAL_GATEWAY,
    STATUS_COMPLETED,
    STATUS_ABANDONED,
    STATUS_EXPIRED_INACTIVE,
    STATUS_TERMINATED,
}

# Terminal states that cannot silently resume (Part 22)
TERMINAL_STATUSES: Set[str] = {
    STATUS_COMPLETED,
    STATUS_ABANDONED,
    STATUS_EXPIRED_INACTIVE,
    STATUS_TERMINATED,
}

# Valid stage progression pairs (Part 6)
VALID_STAGE_TRANSITIONS: Set[Tuple[str, str]] = {
    # Purchase progression
    (STAGE_DISCOVERY, STAGE_PRODUCT),
    (STAGE_DISCOVERY, STAGE_CART),
    (STAGE_PRODUCT, STAGE_CART),
    (STAGE_PRODUCT, STAGE_CHECKOUT),
    (STAGE_CART, STAGE_CHECKOUT),
    (STAGE_CHECKOUT, STAGE_PAYMENT),
    (STAGE_PAYMENT, STAGE_CONFIRMATION),
    (STAGE_CHECKOUT, STAGE_CONFIRMATION),
    # Same stage sub-steps (e.g. checkout step 1 -> step 2)
    (STAGE_CHECKOUT, STAGE_CHECKOUT),
    (STAGE_CART, STAGE_CART),
    (STAGE_PAYMENT, STAGE_PAYMENT),
    # Cancellation progression
    (STAGE_SUBSCRIPTION, STAGE_CANCELLATION),
    (STAGE_CANCELLATION, STAGE_RETENTION_STEP),
    (STAGE_RETENTION_STEP, STAGE_CANCELLATION),
    (STAGE_RETENTION_STEP, STAGE_RETENTION_STEP),
    (STAGE_CANCELLATION, STAGE_TERMINATION),
    (STAGE_RETENTION_STEP, STAGE_TERMINATION),
    (STAGE_CANCELLATION, STAGE_CANCELLATION),
    (STAGE_RETENTION_STEP, STAGE_SUBSCRIPTION),  # Retention accepted (stay with service)
}

# Phase B5.6 Transition Policies (Gate-2 Architecture)
TRANSITION_VALID: str = "VALID"
TRANSITION_UNEXPECTED: str = "UNEXPECTED"
TRANSITION_IMPOSSIBLE: str = "IMPOSSIBLE"

# Legitimate shortcuts or non-standard paths (Gate-2 Section 8)
UNEXPECTED_STAGE_TRANSITIONS: Set[Tuple[str, str]] = {
    (STAGE_PRODUCT, STAGE_PAYMENT),       # 1-Click / Express Buy (Apple Pay, Buy Now)
    (STAGE_DISCOVERY, STAGE_PAYMENT),     # Direct listing purchase
    (STAGE_DISCOVERY, STAGE_CHECKOUT),    # Direct checkout shortcut
    (STAGE_PAYMENT, STAGE_CART),          # User cleared/edited cart from payment
    (STAGE_RETENTION_STEP, STAGE_DISCOVERY),  # User aborted cancellation, returned to catalog
    (STAGE_SUBSCRIPTION, STAGE_RETENTION_STEP), # Direct retention gate upon cancellation attempt
    (STAGE_CHECKOUT, STAGE_CART),         # Navigation back to cart from checkout
    (STAGE_PAYMENT, STAGE_CHECKOUT),      # Navigation back to shipping/details from payment
}

# Structurally contradictory or invalid reverse jumps (Gate-2 Section 8)
IMPOSSIBLE_STAGE_TRANSITIONS: Set[Tuple[str, str]] = {
    (STAGE_CONFIRMATION, STAGE_PAYMENT),     # Re-paying for finished order
    (STAGE_CONFIRMATION, STAGE_CHECKOUT),    # Re-entering checkout of finished order
    (STAGE_CONFIRMATION, STAGE_CART),        # Re-entering cart of finished order
    (STAGE_CONFIRMATION, STAGE_PRODUCT),     # Re-entering product of finished order
    (STAGE_CONFIRMATION, STAGE_DISCOVERY),   # Re-entering discovery of finished order
    (STAGE_TERMINATION, STAGE_RETENTION_STEP), # Retention offer after final termination
    (STAGE_TERMINATION, STAGE_CANCELLATION),   # Cancelling already terminated account
    (STAGE_TERMINATION, STAGE_CHECKOUT),     # Terminated jumping to purchase checkout
    (STAGE_TERMINATION, STAGE_PRODUCT),
    (STAGE_TERMINATION, STAGE_CART),
    (STAGE_CANCELLATION, STAGE_CONFIRMATION),
    (STAGE_RETENTION_STEP, STAGE_CONFIRMATION),
    (STAGE_PAYMENT, STAGE_DISCOVERY),
    (STAGE_CHECKOUT, STAGE_DISCOVERY),
}

# Directed Context Compatibility Matrix (Gate-2 Section E)
ALLOWED_CONTEXT_TRANSITIONS: Dict[str, Set[str]] = {
    "discovery": {"discovery", "purchase", "subscription", "unknown"},
    "purchase": {"purchase", "checkout", "billing", "cart", "consent", "dialog", "unknown"},
    "cart": {"cart", "checkout", "purchase", "discovery", "dialog", "unknown"},
    "checkout": {"checkout", "billing", "payment", "purchase", "cart", "consent", "dialog", "unknown"},
    "billing": {"billing", "payment", "checkout", "purchase", "dialog", "unknown"},
    "payment": {"payment", "billing", "checkout", "purchase", "dialog", "unknown"},
    "subscription": {"subscription", "cancellation", "membership", "renewal", "billing", "dialog", "unknown"},
    "cancellation": {"cancellation", "retention", "subscription", "membership", "account_deletion", "dialog", "unknown"},
    "membership": {"membership", "cancellation", "subscription", "renewal", "dialog", "unknown"},
    "renewal": {"renewal", "subscription", "billing", "cancellation", "dialog", "unknown"},
    "consent": {"consent", "checkout", "purchase", "subscription", "unknown"},
    "dialog": {"dialog", "checkout", "payment", "cancellation", "subscription", "purchase", "unknown"},
    "unknown": {"discovery", "purchase", "cart", "checkout", "billing", "payment", "subscription", "cancellation", "unknown"},
}

# Product Anchor Quality Tiers (Gate-2 Section 10)
ANCHOR_STRONG: str = "STRONG"
ANCHOR_MODERATE: str = "MODERATE"
ANCHOR_WEAK: str = "WEAK"
ANCHOR_UNKNOWN: str = "UNKNOWN"

ANCHOR_TIER_RANK: Dict[str, int] = {
    ANCHOR_UNKNOWN: 0,
    ANCHOR_WEAK: 1,
    ANCHOR_MODERATE: 2,
    ANCHOR_STRONG: 3,
}

# Known 2-level TLD suffixes for eTLD+1 extraction
TWO_LEVEL_TLDS: Set[str] = {
    "co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk",
    "co.in", "net.in", "org.in", "gen.in", "firm.in",
    "com.au", "net.au", "org.au", "edu.au",
    "co.nz", "net.nz", "org.nz",
    "com.br", "net.br", "org.br",
    "co.jp", "ne.jp", "or.jp",
    "co.za", "org.za",
    "com.sg", "edu.sg",
    "com.my", "org.my",
}


def make_journey_id() -> str:
    """Generate an opaque immutable journey identifier (Part 2).

    Format: jrn_<uuid4 hex>
    No semantic attributes (origin, tab, intent, stage) are encoded.
    """
    return f"jrn_{uuid.uuid4().hex}"


def extract_site_identity(url_or_host: Optional[str]) -> str:
    """Extract registrable domain / eTLD+1 site identity (Part 8).

    Examples:
    - https://shop.example.com/item -> example.com
    - secure.checkout.example.co.uk -> example.co.uk
    - localhost:8000 -> localhost
    """
    if not url_or_host:
        return "unknown_site"

    target = url_or_host.strip().lower()
    if "://" in target:
        try:
            parsed = urlparse(target)
            target = parsed.netloc or parsed.path
        except Exception:
            pass

    # Strip port if present
    host = target.split(":")[0].strip("/")
    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return host or "localhost"

    parts = host.split(".")
    if len(parts) <= 2:
        return host

    # Check 2-level TLDs (e.g. example.co.uk)
    last_two = ".".join(parts[-2:])
    if last_two in TWO_LEVEL_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])

    return ".".join(parts[-2:])


class JourneyTimeoutConfig(BaseModel):
    """Configurable Inactivity & Grace Timeouts (Gate-2 Section 18)."""
    soft_idle_timeout_ms: int = Field(default=JOURNEY_SOFT_IDLE_TIMEOUT_MS, description="Soft idle timeout (ms)")
    journey_expiration_timeout_ms: int = Field(default=JOURNEY_INACTIVITY_TIMEOUT_MS, description="Hard expiration timeout (ms)")
    gateway_grace_timeout_ms: int = Field(default=30 * 60 * 1000, description="Gateway grace timeout (ms)")


class TransactionLedgerEntry(BaseModel):
    """Immutable audit record for a stage visit (Gate-2 Section 15)."""
    stage: str = Field(..., description="Stage visited")
    route: Optional[str] = Field(None, description="Route or path")
    timestamp: float = Field(default=0.0, description="Timestamp ms")
    product_anchor: Optional[str] = Field(None, description="Active product anchor")
    anchor_tier: str = Field(default=ANCHOR_UNKNOWN, description="Active anchor tier")
    price_disclosed: Optional[float] = Field(None, description="Price disclosed if any")
    currency: Optional[str] = Field(None, description="Currency code if any")


class TransactionLedger(BaseModel):
    """Deterministic transaction audit ledger (Gate-2 Section 15)."""
    entries: List[TransactionLedgerEntry] = Field(default_factory=list)

    def record_stage(
        self,
        stage: str,
        route: Optional[str] = None,
        timestamp: float = 0.0,
        product_anchor: Optional[str] = None,
        anchor_tier: str = ANCHOR_UNKNOWN,
        price_disclosed: Optional[float] = None,
        currency: Optional[str] = None,
    ) -> None:
        """Append an immutable audit entry."""
        self.entries.append(
            TransactionLedgerEntry(
                stage=stage,
                route=route,
                timestamp=timestamp,
                product_anchor=product_anchor,
                anchor_tier=anchor_tier,
                price_disclosed=price_disclosed,
                currency=currency,
            )
        )


class JourneyState(BaseModel):
    """Deterministic Journey State Object (Part 4 & Phase B5.6)."""
    journey_id: str = Field(..., description="Opaque immutable journey ID (jrn_<uuid4 hex>)")
    tab_id: Optional[int] = Field(None, description="Physical browser tab container ID")
    session_id: Optional[str] = Field(None, description="Extension/browser session ID")
    site_identity: str = Field(default="unknown_site", description="Registrable domain / eTLD+1")
    intent_type: str = Field(default="GENERAL", description="Consumer intent: PURCHASE, CANCELLATION, etc.")
    journey_stage: str = Field(default=STAGE_UNKNOWN, description="Current canonical stage in journey")
    stage_history: List[str] = Field(default_factory=list, description="Sequence of visited stages (immutable sequence)")
    status: str = Field(default=STATUS_ACTIVE, description="Lifecycle status")
    product_anchor: Optional[str] = Field(None, description="Non-sensitive product SKU, ID or title slug")
    anchor_tier: str = Field(default=ANCHOR_UNKNOWN, description="Quality tier of current product anchor")
    has_commitment: bool = Field(default=False, description="True once consumer commits past browsing into cart/checkout")
    ledger: List[Dict[str, Any]] = Field(default_factory=list, description="Immutable transaction audit ledger entries")
    last_event_timestamp: float = Field(default=0.0, description="Timestamp of last recorded event (ms)")
    created_timestamp: float = Field(default=0.0, description="Timestamp when journey was initialized (ms)")


class JourneyEngine:
    """Deterministic Multi-Page Journey Boundary & Continuity Engine (Phase B5.4 & B5.6)."""

    def __init__(self, timeout_config: Optional[JourneyTimeoutConfig] = None) -> None:
        self.timeouts = timeout_config or JourneyTimeoutConfig()

    @staticmethod
    def are_in_same_journey(
        item_a: EvidenceItem,
        item_b: EvidenceItem,
    ) -> Optional[bool]:
        """Determine whether two evidence items belong to the same transaction journey."""
        if item_a.is_auxiliary or item_b.is_auxiliary:
            return False

        if item_a.journey_id is not None and item_b.journey_id is not None:
            return item_a.journey_id == item_b.journey_id

        return None

    @staticmethod
    def classify_stage_transition(
        stage_before: Optional[str],
        stage_after: Optional[str],
    ) -> str:
        """Classify stage transition policy: VALID, UNEXPECTED, or IMPOSSIBLE (Gate-2 Section 8)."""
        if not stage_before or not stage_after:
            return TRANSITION_VALID
        s_b = stage_before.upper()
        s_a = stage_after.upper()
        if s_b == STAGE_UNKNOWN or s_a == STAGE_UNKNOWN:
            return TRANSITION_VALID

        # Exact self-transitions (e.g. sub-steps) are VALID
        if s_b == s_a:
            # PRODUCT -> PRODUCT with different items is browsing, handled by anchor comparison
            return TRANSITION_VALID

        pair = (s_b, s_a)
        if pair in IMPOSSIBLE_STAGE_TRANSITIONS:
            return TRANSITION_IMPOSSIBLE
        if pair in VALID_STAGE_TRANSITIONS:
            return TRANSITION_VALID
        if pair in UNEXPECTED_STAGE_TRANSITIONS:
            return TRANSITION_UNEXPECTED

        # Reverse jumps to previous stages during checkout are UNEXPECTED (back navigation)
        if (s_b in (STAGE_CHECKOUT, STAGE_PAYMENT) and s_a in (STAGE_CART, STAGE_PRODUCT)):
            return TRANSITION_UNEXPECTED

        return TRANSITION_IMPOSSIBLE

    @staticmethod
    def is_valid_stage_transition(
        stage_before: Optional[str],
        stage_after: Optional[str],
    ) -> bool:
        """Verify whether stage transition is acceptable for forward continuity (B5.4 contract)."""
        if not stage_before or not stage_after:
            return True
        s_b = stage_before.upper()
        s_a = stage_after.upper()
        if s_b == STAGE_UNKNOWN or s_a == STAGE_UNKNOWN:
            return True
        if s_b == STAGE_PRODUCT and s_a == STAGE_PRODUCT:
            return False
        return (s_b, s_a) in VALID_STAGE_TRANSITIONS

    @staticmethod
    def context_transition_is_allowed(
        ctx_before: Optional[str],
        ctx_after: Optional[str],
    ) -> bool:
        """Check directed context transition compatibility (Gate-2 Section E)."""
        if not ctx_before or not ctx_after:
            return True
        cb = str(ctx_before).strip().lower()
        ca = str(ctx_after).strip().lower()
        if cb == ca:
            return True

        allowed_targets = ALLOWED_CONTEXT_TRANSITIONS.get(cb)
        if allowed_targets is not None:
            return ca in allowed_targets

        # If origin context is unmapped, permit standard transitions to prevent false blocks
        return True

    @staticmethod
    def refine_product_anchor(
        existing_anchor: Optional[str],
        existing_tier: Optional[str],
        new_anchor: Optional[str],
        new_tier: Optional[str],
    ) -> Tuple[Optional[str], str]:
        """Refine product anchor preserving observation immutability (Gate-2 Section 6 & 10).
        
        Rules:
        - Weak -> Moderate -> Strong refinement allowed.
        - Strong cannot be overwritten by Weak or Moderate.
        - Returns (refined_anchor, refined_tier).
        """
        ex_t = existing_tier or ANCHOR_UNKNOWN
        nw_t = new_tier or ANCHOR_UNKNOWN
        ex_rank = ANCHOR_TIER_RANK.get(ex_t, 0)
        nw_rank = ANCHOR_TIER_RANK.get(nw_t, 0)

        if not existing_anchor:
            return new_anchor, nw_t

        if not new_anchor:
            return existing_anchor, ex_t

        # Strong anchor conflict
        if ex_t == ANCHOR_STRONG and nw_t == ANCHOR_STRONG:
            if existing_anchor.strip().lower() != new_anchor.strip().lower():
                # Conflicting strong anchor: keep existing, report conflict upstream
                return existing_anchor, ex_t

        # Upward refinement
        if nw_rank > ex_rank:
            return new_anchor, nw_t

        return existing_anchor, ex_t

    @staticmethod
    def reconcile_gateway_return(
        journey: JourneyState,
        return_url: str,
        target_stage: Optional[str],
        target_route: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reconcile external gateway return using multi-signal verification (Gate-2 Section 5 & I)."""
        if journey.status != STATUS_SUSPENDED_EXTERNAL_GATEWAY:
            return {
                "continuity": "UNKNOWN",
                "status": journey.status,
                "reason": "Journey was not suspended for external gateway",
            }

        route = (target_route or return_url or "").lower()
        stage = (target_stage or "").upper()

        is_confirmation = (
            stage == STAGE_CONFIRMATION
            or any(k in route for k in ("confirm", "success", "receipt", "thank", "order-complete"))
        )
        is_retry = (
            stage in (STAGE_PAYMENT, STAGE_CHECKOUT)
            or any(k in route for k in ("pay", "billing", "checkout", "retry", "declined"))
        )
        is_homepage_or_discovery = (
            stage == STAGE_DISCOVERY
            or route.strip() in ("/", "", "#", "/index.html")
            or any(k in route for k in ("shop", "catalog", "category", "search"))
        )

        if is_confirmation:
            journey.status = STATUS_COMPLETED
            journey.journey_stage = STAGE_CONFIRMATION
            return {
                "continuity": "RESUMED_COMPLETED",
                "status": STATUS_COMPLETED,
                "stage": STAGE_CONFIRMATION,
                "reason": "Multi-signal return confirms completed transaction",
            }
        elif is_retry:
            journey.status = STATUS_ACTIVE
            journey.journey_stage = STAGE_PAYMENT
            return {
                "continuity": "RESUMED_RETRY",
                "status": STATUS_ACTIVE,
                "stage": STAGE_PAYMENT,
                "reason": "Gateway return landed on retry/checkout state",
            }
        elif is_homepage_or_discovery:
            journey.status = STATUS_IDLE
            return {
                "continuity": "RESUMED_ABORTED",
                "status": STATUS_IDLE,
                "stage": journey.journey_stage,
                "reason": "Gateway return landed on homepage/discovery without confirmation",
            }

        return {
            "continuity": "UNKNOWN",
            "status": journey.status,
            "reason": "Ambiguous gateway return target",
        }

    @staticmethod
    def evaluate_inactivity_status(
        last_event_ms: float,
        current_time_ms: float,
        timeout_config: Optional[JourneyTimeoutConfig] = None,
    ) -> str:
        """Evaluate journey status based on elapsed inactivity."""
        if last_event_ms <= 0:
            return STATUS_ACTIVE
        cfg = timeout_config or JourneyTimeoutConfig()
        elapsed = current_time_ms - last_event_ms
        if elapsed >= cfg.journey_expiration_timeout_ms:
            return STATUS_EXPIRED_INACTIVE
        if elapsed >= cfg.soft_idle_timeout_ms:
            return STATUS_IDLE
        return STATUS_ACTIVE
