"""backend/services/regulatory_engine.py
ClauseGuard Phase B5.8 — Regulatory Check Engine.
Deterministic, jurisdiction-aware, versioned regulatory rule matching layer.

CRITICAL INVARIANTS:
1. Zero LLM for regulatory determination.
2. Absolutely no legal conclusions ('violates the law', 'illegal' prohibited).
3. Structured rule registry with verified authoritative citations only (no fabricated laws).
4. Jurisdiction must never be guessed; unknown jurisdiction produces UNKNOWN status.
5. Mandatory effective-date validation (future/expired regulations do not apply).
6. Missing transaction date prevents SUPPORTED status.
7. Strict provenance: supporting_evidence_ids must map to actual input EvidenceItem IDs.
8. Risk score isolation: Regulatory findings are purely informational for Phase B5.9 and
   must NOT modify existing risk scores or thresholds.
9. Deterministic deduplication and stable sorted outputs.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.schemas.evidence import (
    ContradictionItem,
    EvidenceItem,
    IntelligenceAnalysisResponse,
    PatternAssessment,
    TemporalRelationshipItem,
)
from backend.schemas.regulatory import (
    ApplicabilityType,
    RegulatoryCheckRequest,
    RegulatoryCheckResponse,
    RegulatoryFinding,
    RegulatoryStatusType,
)

# Canonical Pattern Taxonomy constants (aligned with B5.7)
PATTERN_SUBSCRIPTION_TRAP = "SUBSCRIPTION_TRAP"
PATTERN_DRIP_PRICING = "DRIP_PRICING"
PATTERN_BASKET_SNAKING = "BASKET_SNAKING"
PATTERN_FALSE_URGENCY = "FALSE_URGENCY"
PATTERN_SCARCITY = "SCARCITY"
PATTERN_FORCED_ACTION = "FORCED_ACTION"
PATTERN_CONFIRM_SHAMING = "CONFIRM_SHAMING"
PATTERN_OBSTRUCTION = "OBSTRUCTION"
PATTERN_MISDIRECTION = "MISDIRECTION"
PATTERN_SOCIAL_PROOF = "SOCIAL_PROOF"

# Status Constants
STATUS_NOT_APPLICABLE: RegulatoryStatusType = "NOT_APPLICABLE"
STATUS_POTENTIALLY_RELEVANT: RegulatoryStatusType = "POTENTIALLY_RELEVANT"
STATUS_SUPPORTED: RegulatoryStatusType = "SUPPORTED"
STATUS_UNKNOWN: RegulatoryStatusType = "UNKNOWN"
STATUS_UNSUPPORTED_RULE: RegulatoryStatusType = "UNSUPPORTED_RULE"

APPLICABLE: ApplicabilityType = "APPLICABLE"
NOT_APPLICABLE: ApplicabilityType = "NOT_APPLICABLE"
UNKNOWN_APPLICABILITY: ApplicabilityType = "UNKNOWN"

STATUS_PRIORITY: Dict[RegulatoryStatusType, int] = {
    STATUS_SUPPORTED: 4,
    STATUS_POTENTIALLY_RELEVANT: 3,
    STATUS_UNKNOWN: 2,
    STATUS_UNSUPPORTED_RULE: 1,
    STATUS_NOT_APPLICABLE: 1,
}

# Forbidden Legal Conclusion Phrases
FORBIDDEN_LEGAL_PHRASES = (
    "violates the law",
    "violate the law",
    "violation of law",
    "breaking the law",
    "breaks the law",
    "is illegal",
    "are illegal",
    "illegal",
    "unlawful conduct",
    "found guilty",
    "legally confirmed",
)


class RegistryRule:
    """Structured, immutable representation of an authoritative regulatory provision."""

    def __init__(
        self,
        regulation_id: str,
        rule_id: str,
        jurisdiction: str,
        rule_name: str,
        pattern: str,
        effective_from: Optional[str],
        effective_to: Optional[str],
        applicability_conditions: Dict[str, Any],
        authoritative_source: str,
        version: str = "1.0.0",
        regulated_entity_type: Optional[str] = None,
        service_scope: Optional[str] = None,
        requires_entity_scope: bool = False,
        authority_type: Optional[str] = None,
        requires_member_state_mapping: bool = False,
        mapping_type: Optional[str] = None,
    ):
        self.regulation_id = regulation_id
        self.rule_id = rule_id
        self.jurisdiction = jurisdiction.upper()
        self.rule_name = rule_name
        self.pattern = pattern
        self.effective_from = effective_from
        self.effective_to = effective_to
        self.applicability_conditions = applicability_conditions
        self.authoritative_source = authoritative_source
        self.version = version
        self.regulated_entity_type = regulated_entity_type
        self.service_scope = service_scope
        self.requires_entity_scope = requires_entity_scope
        self.authority_type = authority_type
        self.requires_member_state_mapping = requires_member_state_mapping
        self.mapping_type = mapping_type


class RuleRegistry:
    """Versioned structured registry of authoritative digital consumer protection regulations."""

    def __init__(self) -> None:
        self._rules: List[RegistryRule] = []
        self._load_authoritative_rules()

    @property
    def supported_jurisdictions(self) -> Set[str]:
        """Return the set of jurisdiction codes with configured rules."""
        return {r.jurisdiction for r in self._rules}

    def _load_authoritative_rules(self) -> None:
        """Load verified statutory regulations across supported jurisdictions.
        
        Sources used:
        - India: CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023 (F. No. CCPA-1/1/2023-CCPA).
        - European Union: Digital Services Act (Regulation (EU) 2022/2065) & UCPD (Directive 2005/29/EC).
        - United States: FTC Act Section 5 (15 U.S.C. § 45), ROSCA (15 U.S.C. § 8403), California ARL (§ 17602).
        - United Kingdom: Digital Markets, Competition and Consumers Act 2024 (DMCC Act 2024).
        - Historical / Testing: Repealed 1986 Indian CPA (for expiry validation) and 2026 EU AI Act (for future validation).
        """
        # ---------------------------------------------------------------------
        # INDIA (IN) — CCPA Dark Patterns Guidelines, 2023
        # Effective: 2023-11-30
        # ---------------------------------------------------------------------
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_DRIP_PRICING",
                jurisdiction="IN",
                rule_name="Prohibition of Drip Pricing",
                pattern=PATTERN_DRIP_PRICING,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 5",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_SUBSCRIPTION_TRAP",
                jurisdiction="IN",
                rule_name="Prohibition of Subscription Traps",
                pattern=PATTERN_SUBSCRIPTION_TRAP,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 3",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_BASKET_SNAKING",
                jurisdiction="IN",
                rule_name="Prohibition of Basket Sneaking",
                pattern=PATTERN_BASKET_SNAKING,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 4",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_FALSE_URGENCY",
                jurisdiction="IN",
                rule_name="Prohibition of False Urgency",
                pattern=PATTERN_FALSE_URGENCY,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 1",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_CONFIRM_SHAMING",
                jurisdiction="IN",
                rule_name="Prohibition of Confirm Shaming",
                pattern=PATTERN_CONFIRM_SHAMING,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 2",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_FORCED_ACTION",
                jurisdiction="IN",
                rule_name="Prohibition of Forced Action",
                pattern=PATTERN_FORCED_ACTION,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 7",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_OBSTRUCTION",
                jurisdiction="IN",
                rule_name="Prohibition of Interface Interference and Obstruction",
                pattern=PATTERN_OBSTRUCTION,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 6",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_MISDIRECTION",
                jurisdiction="IN",
                rule_name="Prohibition of Misdirection",
                pattern=PATTERN_MISDIRECTION,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 8",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_SCARCITY",
                jurisdiction="IN",
                rule_name="Prohibition of Fabricated Scarcity",
                pattern=PATTERN_SCARCITY,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 1",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CCPA_DP_2023",
                rule_id="IN_CCPA_SOCIAL_PROOF",
                jurisdiction="IN",
                rule_name="Prohibition of Deceptive Social Proof and Disguised Advertising",
                pattern=PATTERN_SOCIAL_PROOF,
                effective_from="2023-11-30",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023, Annexure 1, Clause 12",
                authority_type="STATUTORY_GUIDELINES",
                regulated_entity_type="TRADER_OR_PLATFORM",
                service_scope="ECOMMERCE_AND_DIGITAL_SERVICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )

        # ---------------------------------------------------------------------
        # EUROPEAN UNION (EU) — Digital Services Act & UCPD
        # Effective: 2022-11-16 (DSA Article 25) / 2022-05-28 (UCPD)
        # ---------------------------------------------------------------------
        self._rules.append(
            RegistryRule(
                regulation_id="EU_DSA_2022_2065",
                rule_id="EU_DSA_ART25_DECEPTIVE_DESIGN",
                jurisdiction="EU",
                rule_name="Online Interface Deceptive Architecture and Misdirection",
                pattern=PATTERN_MISDIRECTION,
                effective_from="2022-11-16",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Regulation (EU) 2022/2065 (Digital Services Act), Article 25(1)",
                authority_type="EU_REGULATION",
                regulated_entity_type="ONLINE_PLATFORM",
                service_scope="PROVIDERS_OF_ONLINE_PLATFORMS",
                requires_entity_scope=True,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="EU_DSA_2022_2065",
                rule_id="EU_DSA_ART25_CANCELLATION",
                jurisdiction="EU",
                rule_name="Termination and Off-Boarding Obstruction",
                pattern=PATTERN_OBSTRUCTION,
                effective_from="2022-11-16",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Regulation (EU) 2022/2065 (Digital Services Act), Article 25(1)(b)",
                authority_type="EU_REGULATION",
                regulated_entity_type="ONLINE_PLATFORM",
                service_scope="PROVIDERS_OF_ONLINE_PLATFORMS",
                requires_entity_scope=True,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="EU_UCPD_2005_29",
                rule_id="EU_UCPD_DRIP_PRICING",
                jurisdiction="EU",
                rule_name="Misleading Price Omission and Additional Charges",
                pattern=PATTERN_DRIP_PRICING,
                effective_from="2022-05-28",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Directive 2005/29/EC (amended by Directive (EU) 2019/2161), Article 7(4)(c)",
                authority_type="EU_DIRECTIVE",
                requires_member_state_mapping=True,
                regulated_entity_type="TRADER",
                service_scope="B2C_COMMERCIAL_PRACTICES",
                mapping_type="DIRECTIVE_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="EU_UCPD_2005_29",
                rule_id="EU_UCPD_FALSE_URGENCY",
                jurisdiction="EU",
                rule_name="Misleading Limited-Time Availability Claims",
                pattern=PATTERN_FALSE_URGENCY,
                effective_from="2022-05-28",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED"]},
                authoritative_source="Directive 2005/29/EC, Annex I, Point 7",
                authority_type="EU_DIRECTIVE",
                requires_member_state_mapping=True,
                regulated_entity_type="TRADER",
                service_scope="B2C_COMMERCIAL_PRACTICES",
                mapping_type="DIRECTIVE_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="EU_DSA_2022_2065",
                rule_id="EU_DSA_ART25_CONFIRM_SHAMING",
                jurisdiction="EU",
                rule_name="Prohibition of Subverting Autonomy Through Confirm Shaming",
                pattern=PATTERN_CONFIRM_SHAMING,
                effective_from="2022-11-16",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Regulation (EU) 2022/2065 (Digital Services Act), Article 25(1)",
                authority_type="EU_REGULATION",
                regulated_entity_type="ONLINE_PLATFORM",
                service_scope="PROVIDERS_OF_ONLINE_PLATFORMS",
                requires_entity_scope=True,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="EU_DSA_2022_2065",
                rule_id="EU_DSA_ART25_FORCED_ACTION",
                jurisdiction="EU",
                rule_name="Interface Manipulation Requiring Unrelated Forced Actions",
                pattern=PATTERN_FORCED_ACTION,
                effective_from="2022-11-16",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Regulation (EU) 2022/2065 (Digital Services Act), Article 25(1)",
                authority_type="EU_REGULATION",
                regulated_entity_type="ONLINE_PLATFORM",
                service_scope="PROVIDERS_OF_ONLINE_PLATFORMS",
                requires_entity_scope=True,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="EU_UCPD_2005_29",
                rule_id="EU_UCPD_SCARCITY",
                jurisdiction="EU",
                rule_name="Falsely Stating Availability of Products and False Scarcity",
                pattern=PATTERN_SCARCITY,
                effective_from="2022-05-28",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Directive 2005/29/EC, Annex I, Point 7",
                authority_type="EU_DIRECTIVE",
                requires_member_state_mapping=True,
                regulated_entity_type="TRADER",
                service_scope="B2C_COMMERCIAL_PRACTICES",
                mapping_type="DIRECTIVE_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="EU_UCPD_2005_29",
                rule_id="EU_UCPD_BASKET_SNAKING",
                jurisdiction="EU",
                rule_name="Inertia Selling and Default Pre-Selected Add-Ons",
                pattern=PATTERN_BASKET_SNAKING,
                effective_from="2022-05-28",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Directive 2005/29/EC, Annex I, Point 29",
                authority_type="EU_DIRECTIVE",
                requires_member_state_mapping=True,
                regulated_entity_type="TRADER",
                service_scope="B2C_COMMERCIAL_PRACTICES",
                mapping_type="DIRECTIVE_PROHIBITION",
            )
        )

        # ---------------------------------------------------------------------
        # UNITED STATES (US) — FTC Act, ROSCA, California ARL
        # ---------------------------------------------------------------------
        self._rules.append(
            RegistryRule(
                regulation_id="US_ROSCA_2010",
                rule_id="US_ROSCA_NEGATIVE_OPTION",
                jurisdiction="US",
                rule_name="Negative Option Feature Clear Disclosures and Simple Cancellation",
                pattern=PATTERN_SUBSCRIPTION_TRAP,
                effective_from="2010-12-29",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Restore Online Shoppers' Confidence Act (ROSCA), 15 U.S.C. § 8403",
                authority_type="STATUTE",
                regulated_entity_type="ONLINE_SELLER",
                service_scope="INTERNET_TRANSACTIONS",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="US_FTC_ACT",
                rule_id="US_FTC_ACT_SEC5_DECEPTIVE",
                jurisdiction="US",
                rule_name="Unfair or Deceptive Acts or Practices (Pricing Practices)",
                pattern=PATTERN_DRIP_PRICING,
                effective_from="1914-09-26",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Federal Trade Commission Act, 15 U.S.C. § 45(a)(1)",
                authority_type="GENERAL_CONSUMER_PROTECTION_AUTHORITY",
                regulated_entity_type="COMMERCE_ENTITY",
                service_scope="INTERSTATE_COMMERCE",
                requires_entity_scope=False,
                mapping_type="POTENTIAL_APPLICABILITY",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="US_CAL_ARL",
                rule_id="US_CAL_ARL_SUBSCRIPTION",
                jurisdiction="US",
                rule_name="Automatic Renewal Clear Notice and Online Cancellation",
                pattern=PATTERN_SUBSCRIPTION_TRAP,
                effective_from="2022-07-01",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="California Automatic Renewal Law, Cal. Bus. & Prof. Code § 17602",
                authority_type="STATE_STATUTE",
                regulated_entity_type="BUSINESS",
                service_scope="SUBSCRIPTION_AND_AUTOMATIC_RENEWAL",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="US_FTC_ACT",
                rule_id="US_FTC_ACT_SEC5_FALSE_URGENCY",
                jurisdiction="US",
                rule_name="Unfair or Deceptive Acts or Practices (Urgency Claims)",
                pattern=PATTERN_FALSE_URGENCY,
                effective_from="1914-09-26",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED"]},
                authoritative_source="Federal Trade Commission Act, 15 U.S.C. § 45(a)(1)",
                authority_type="GENERAL_CONSUMER_PROTECTION_AUTHORITY",
                regulated_entity_type="COMMERCE_ENTITY",
                service_scope="INTERSTATE_COMMERCE",
                requires_entity_scope=False,
                mapping_type="POTENTIAL_APPLICABILITY",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="US_FTC_ACT",
                rule_id="US_FTC_ACT_SEC5_OBSTRUCTION",
                jurisdiction="US",
                rule_name="Unfair or Deceptive Acts or Practices (Obstruction Practices)",
                pattern=PATTERN_OBSTRUCTION,
                effective_from="1914-09-26",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Federal Trade Commission Act, 15 U.S.C. § 45(a)(1)",
                authority_type="GENERAL_CONSUMER_PROTECTION_AUTHORITY",
                regulated_entity_type="COMMERCE_ENTITY",
                service_scope="INTERSTATE_COMMERCE",
                requires_entity_scope=False,
                mapping_type="POTENTIAL_APPLICABILITY",
            )
        )

        # ---------------------------------------------------------------------
        # UNITED KINGDOM (UK) — DMCC Act 2024
        # Effective: 2024-05-24
        # ---------------------------------------------------------------------
        self._rules.append(
            RegistryRule(
                regulation_id="UK_DMCC_2024",
                rule_id="UK_DMCC_DRIP_PRICING",
                jurisdiction="UK",
                rule_name="Omission of Mandatory Additional Fees from Headline Price",
                pattern=PATTERN_DRIP_PRICING,
                effective_from="2024-05-24",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Digital Markets, Competition and Consumers Act 2024, Chapter 1",
                authority_type="STATUTE",
                regulated_entity_type="TRADER",
                service_scope="COMMERCIAL_PRACTICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="UK_DMCC_2024",
                rule_id="UK_DMCC_SUBSCRIPTION_TRAPS",
                jurisdiction="UK",
                rule_name="Subscription Contracts Clear Pre-Contract Information",
                pattern=PATTERN_SUBSCRIPTION_TRAP,
                effective_from="2024-05-24",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Digital Markets, Competition and Consumers Act 2024, Chapter 2",
                authority_type="STATUTE",
                regulated_entity_type="TRADER",
                service_scope="SUBSCRIPTION_CONTRACTS",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="UK_DMCC_2024",
                rule_id="UK_DMCC_FALSE_URGENCY",
                jurisdiction="UK",
                rule_name="Deceptive Countdown Timers and Misleading Time Limits",
                pattern=PATTERN_FALSE_URGENCY,
                effective_from="2024-05-24",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED"]},
                authoritative_source="Digital Markets, Competition and Consumers Act 2024, Schedule 19, Paragraph 7",
                authority_type="STATUTE",
                regulated_entity_type="TRADER",
                service_scope="COMMERCIAL_PRACTICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )
        self._rules.append(
            RegistryRule(
                regulation_id="UK_DMCC_2024",
                rule_id="UK_DMCC_FAKE_REVIEWS",
                jurisdiction="UK",
                rule_name="Submitting or Commissioning Fake Consumer Reviews and Deceptive Social Proof",
                pattern=PATTERN_SOCIAL_PROOF,
                effective_from="2024-05-24",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Digital Markets, Competition and Consumers Act 2024, Schedule 19, Paragraph 23",
                authority_type="STATUTE",
                regulated_entity_type="TRADER",
                service_scope="COMMERCIAL_PRACTICES",
                requires_entity_scope=False,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )

        # ---------------------------------------------------------------------
        # EXPIRED REGULATION TEST BENCHMARK
        # Repealed Indian Consumer Protection Act 1986 (Effective 1987-07-01 to 2020-07-20)
        # ---------------------------------------------------------------------
        self._rules.append(
            RegistryRule(
                regulation_id="IN_CPA_1986",
                rule_id="IN_CPA_1986_UNFAIR_TRADE",
                jurisdiction="IN",
                rule_name="Unfair Trade Practices (Repealed 1986 Act)",
                pattern=PATTERN_MISDIRECTION,
                effective_from="1987-07-01",
                effective_to="2020-07-20",
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Consumer Protection Act, 1986, Section 2(1)(r) (Repealed 2020-07-20)",
                authority_type="REPEALED_STATUTE",
                regulated_entity_type="TRADER",
                service_scope="TRADE_PRACTICES",
                requires_entity_scope=False,
                mapping_type="EXPIRED_PROHIBITION",
            )
        )

        # ---------------------------------------------------------------------
        # FUTURE REGULATION TEST BENCHMARK
        # EU AI Act Article 50 Transparency Obligations (Effective 2026-08-02)
        # ---------------------------------------------------------------------
        self._rules.append(
            RegistryRule(
                regulation_id="EU_AI_ACT_2024",
                rule_id="EU_AI_ACT_ART50_TRANSPARENCY",
                jurisdiction="EU",
                rule_name="AI Interaction Transparency Obligations",
                pattern=PATTERN_MISDIRECTION,
                effective_from="2026-08-02",
                effective_to=None,
                applicability_conditions={"pattern_statuses": ["SUPPORTED", "POTENTIAL"]},
                authoritative_source="Regulation (EU) 2024/1689 (Artificial Intelligence Act), Article 50",
                authority_type="EU_REGULATION",
                regulated_entity_type="AI_SYSTEM_PROVIDER",
                service_scope="AI_INTERACTION",
                requires_entity_scope=True,
                mapping_type="SPECIFIC_STATUTORY_PROHIBITION",
            )
        )

    def get_all_rules(self) -> List[RegistryRule]:
        """Return all registered rules."""
        return list(self._rules)

    def get_rules_by_pattern(self, pattern: str) -> List[RegistryRule]:
        """Return rules relevant to a specific dark pattern category."""
        return [r for r in self._rules if r.pattern.upper() == pattern.upper()]

    def get_rules_by_jurisdiction(self, jurisdiction: str) -> List[RegistryRule]:
        """Return rules registered for a given jurisdiction."""
        norm_j = jurisdiction.upper()
        if norm_j == "GB":
            norm_j = "UK"
        return [r for r in self._rules if r.jurisdiction == norm_j]


class JurisdictionResolver:
    """Deterministic, unambiguous resolver for digital transaction jurisdiction."""

    JURISDICTION_NORMALIZATION = {
        "INDIA": "IN",
        "IND": "IN",
        "IN": "IN",
        "EUROPE": "EU",
        "EUROPEAN UNION": "EU",
        "EU": "EU",
        "UNITED STATES": "US",
        "USA": "US",
        "US": "US",
        "UNITED KINGDOM": "UK",
        "GREAT BRITAIN": "UK",
        "GB": "UK",
        "UK": "UK",
    }

    CURRENCY_MAP = {
        "INR": "IN",
        "EUR": "EU",
        "GBP": "UK",
        "USD": "US",
    }

    @classmethod
    def resolve(
        cls,
        explicit_jurisdiction: Optional[str],
        raw_evidence: List[EvidenceItem],
    ) -> Tuple[str, float]:
        """Resolve jurisdiction deterministically without guessing.
        
        Returns:
            Tuple of (resolved_jurisdiction_code, confidence).
            If jurisdiction cannot be resolved with certainty, returns ("UNKNOWN", 0.0).
        """
        # 1. Explicit jurisdiction parameter has highest authority
        if explicit_jurisdiction:
            clean = explicit_jurisdiction.strip().upper()
            if clean in cls.JURISDICTION_NORMALIZATION:
                return cls.JURISDICTION_NORMALIZATION[clean], 1.0
            return clean, 0.90

        # 2. Check evidence items for currency cues (currency is a signal, NOT definitive jurisdiction)
        currency_counts: Dict[str, int] = {}
        for item in raw_evidence:
            curr = getattr(item, "currency", None)
            if curr and isinstance(curr, str):
                c_up = curr.strip().upper()
                if c_up in cls.CURRENCY_MAP:
                    currency_counts[cls.CURRENCY_MAP[c_up]] = currency_counts.get(cls.CURRENCY_MAP[c_up], 0) + 1

        # Conflicting currency signals -> cannot resolve
        if len(currency_counts) > 1:
            return "UNKNOWN", 0.0

        currency_jurisdiction = next(iter(currency_counts.keys())) if len(currency_counts) == 1 else None

        # 3. Check for domain TLD in evidence metadata or descriptions (TLD is a signal, NOT definitive jurisdiction)
        domain_jurisdiction: Optional[str] = None
        for item in raw_evidence:
            ref = getattr(item, "element_ref", "") or ""
            if "?" in ref:
                ref = ref.split("?")[0]
            if "#" in ref:
                ref = ref.split("#")[0]
            desc = getattr(item, "description", "") or ""
            text = f"{desc} {ref}".lower()
            if ".in/" in text or ".in " in text or text.endswith(".in"):
                domain_jurisdiction = "IN"
                break
            if ".co.uk" in text or ".gov.uk" in text:
                domain_jurisdiction = "UK"
                break

        # Corroborated: both currency and domain signals align
        if currency_jurisdiction and domain_jurisdiction:
            if currency_jurisdiction == domain_jurisdiction:
                return currency_jurisdiction, 0.70
            return "UNKNOWN", 0.0

        # Currency only -> heuristic signal, reflects uncertainty (0.60)
        if currency_jurisdiction:
            return currency_jurisdiction, 0.60

        # Domain only -> heuristic signal, reflects uncertainty (0.60)
        if domain_jurisdiction:
            return domain_jurisdiction, 0.60

        # 4. Invariant: Jurisdiction must NEVER be guessed
        return "UNKNOWN", 0.0


class EffectiveDateValidator:
    """Mandatory validator ensuring regulations are applicable within their effective temporal interval."""

    @staticmethod
    def parse_iso_date(date_str: Optional[str]) -> Optional[date]:
        """Safely parse ISO 8601 date string (YYYY-MM-DD) or timestamp."""
        if not date_str:
            return None
        clean = date_str.strip()
        # Extract YYYY-MM-DD substring if timestamp is passed
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", clean)
        if match:
            try:
                y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return date(y, m, d)
            except ValueError:
                return None
        return None

    @classmethod
    def validate(
        cls,
        effective_from: Optional[str],
        effective_to: Optional[str],
        transaction_date_str: Optional[str],
    ) -> Tuple[ApplicabilityType, Optional[str]]:
        """Validate transaction date against regulatory effective dates.
        
        Returns:
            Tuple of (ApplicabilityType, explanation_reason).
        """
        # Missing transaction date cannot establish definitive applicability
        if not transaction_date_str:
            return UNKNOWN_APPLICABILITY, "Transaction date is unverified; temporal applicability cannot be established."

        tx_date = cls.parse_iso_date(transaction_date_str)
        if not tx_date:
            return UNKNOWN_APPLICABILITY, f"Invalid transaction date format: '{transaction_date_str}'."

        ef_date = cls.parse_iso_date(effective_from)
        et_date = cls.parse_iso_date(effective_to)

        # Invariant 9: Future regulations must not apply to earlier transactions
        if ef_date and tx_date < ef_date:
            return NOT_APPLICABLE, f"Transaction date ({tx_date}) predates regulation effective date ({ef_date})."

        # Invariant 10: Expired regulations must not apply outside their effective interval
        if et_date and tx_date > et_date:
            return NOT_APPLICABLE, f"Regulation expired or was superseded on ({et_date}) prior to transaction date ({tx_date})."

        return APPLICABLE, None


class RegulatoryEngine:
    """Authoritative, deterministic regulatory check engine for ClauseGuard Phase B5.8."""

    _registry = RuleRegistry()

    @classmethod
    def evaluate(
        cls,
        intelligence_analysis: Optional[IntelligenceAnalysisResponse],
        raw_evidence: List[EvidenceItem],
        jurisdiction: Optional[str] = None,
        transaction_date: Optional[str] = None,
        journey_id: Optional[str] = None,
        product_id: Optional[str] = None,
        tab_id: Optional[str] = None,
        contradictions: Optional[List[ContradictionItem]] = None,
        temporal_relationships: Optional[List[TemporalRelationshipItem]] = None,
        include_non_applicable: bool = True,
        entity_type: Optional[str] = None,
        member_state: Optional[str] = None,
    ) -> RegulatoryCheckResponse:
        """Evaluate intelligence findings against configured regulatory rules."""
        findings: List[RegulatoryFinding] = []

        def _get_prop(e: Any, prop: str, default: Any = None) -> Any:
            v = getattr(e, prop, None)
            if v is not None:
                return v
            meta = getattr(e, "metadata", {}) or {}
            if isinstance(meta, dict) and prop in meta:
                return meta[prop]
            prov = getattr(e, "provenance", None)
            if prov is not None and hasattr(prov, prop):
                return getattr(prov, prop)
            return default

        # Invariant 24: Auxiliary and isolated gateway context filtering
        commercial_evidence = [
            e for e in raw_evidence
            if not _get_prop(e, "is_auxiliary", False)
            and not _get_prop(e, "is_gateway", False)
            and _get_prop(e, "context_type", "") not in ("gateway", "auxiliary")
        ]
        has_auxiliary_only = len(raw_evidence) > 0 and len(commercial_evidence) == 0
        if has_auxiliary_only:
            # Auxiliary dialogs/isolated events do not produce commercial regulatory findings
            return RegulatoryCheckResponse(
                findings=[],
                jurisdiction_resolved="UNKNOWN",
                jurisdiction_confidence=0.0,
                supported_rule_registry=False,
                rule_available=False,
                requires_jurisdiction=True,
                requires_date=False,
                supporting_evidence=[],
                limitation="Auxiliary dialogs and isolated gateway contexts are excluded from commercial regulatory findings.",
            )

        # Invariant 23: Tab Isolation
        if tab_id is not None:
            commercial_evidence = [
                e for e in commercial_evidence
                if str(_get_prop(e, "tab_id", tab_id)) == str(tab_id)
            ]

        # Invariant 22: Product Isolation
        if product_id is not None:
            commercial_evidence = [
                e for e in commercial_evidence
                if _get_prop(e, "product_id", product_id) in (product_id, None)
            ]

        # Invariant 21: Journey Boundary Isolation
        if journey_id is not None:
            commercial_evidence = [
                e for e in commercial_evidence
                if _get_prop(e, "journey_id", journey_id) in (journey_id, None)
            ]

        # Valid input evidence IDs for strict provenance
        valid_input_ids: Set[str] = {e.evidence_id for e in commercial_evidence}

        # Resolve jurisdiction
        resolved_j, j_conf = JurisdictionResolver.resolve(jurisdiction, commercial_evidence)
        requires_jurisdiction = (resolved_j == "UNKNOWN")
        requires_date = (transaction_date is None or not transaction_date.strip())

        configured_jurisdictions = cls._registry.supported_jurisdictions
        if resolved_j == "UNKNOWN":
            supported_rule_registry = False
            rule_available = False
            limitation = "Transaction jurisdiction could not be resolved from authenticated inputs or contextual signals. Unknown jurisdiction remains UNKNOWN."
        elif resolved_j not in configured_jurisdictions:
            supported_rule_registry = False
            rule_available = False
            limitation = "Jurisdictions outside the configured rule registry are currently unsupported. Unknown jurisdiction remains UNKNOWN. Where a jurisdiction is explicitly established but no configured rule exists, the system must distinguish unsupported rule coverage from unknown jurisdiction."
        else:
            supported_rule_registry = True
            rule_available = True
            limitation = None

        # If intelligence_analysis is not provided, return clean response
        if not intelligence_analysis or not intelligence_analysis.pattern_assessments:
            return RegulatoryCheckResponse(
                findings=[],
                jurisdiction_resolved=resolved_j,
                jurisdiction_confidence=j_conf,
                supported_rule_registry=supported_rule_registry,
                rule_available=rule_available,
                requires_jurisdiction=requires_jurisdiction,
                requires_date=requires_date,
                supporting_evidence=[],
                limitation=limitation,
            )

        # Group pattern assessments by normalized pattern
        assessments_by_pattern: Dict[str, List[PatternAssessment]] = {}
        for a in intelligence_analysis.pattern_assessments:
            pat_norm = a.pattern.strip().upper()
            assessments_by_pattern.setdefault(pat_norm, []).append(a)

        all_rules = cls._registry.get_all_rules()

        # Select candidate rules matching patterns observed in intelligence_analysis
        observed_patterns = set(assessments_by_pattern.keys())
        candidate_rules = [r for r in all_rules if r.pattern.upper() in observed_patterns]

        # Deterministic evaluation across candidate rules
        for rule in candidate_rules:
            pattern_assessments = assessments_by_pattern.get(rule.pattern.upper(), [])

            # Check jurisdiction match
            is_jurisdiction_match = (resolved_j == rule.jurisdiction)
            is_jurisdiction_unknown = (resolved_j == "UNKNOWN")

            # Check effective date
            date_applicability, date_reason = EffectiveDateValidator.validate(
                effective_from=rule.effective_from,
                effective_to=rule.effective_to,
                transaction_date_str=transaction_date,
            )

            # Determine applicability status
            finding = cls._evaluate_single_rule(
                rule=rule,
                assessments=pattern_assessments,
                resolved_jurisdiction=resolved_j,
                jurisdiction_confidence=j_conf,
                is_jurisdiction_match=is_jurisdiction_match,
                is_jurisdiction_unknown=is_jurisdiction_unknown,
                date_applicability=date_applicability,
                date_reason=date_reason,
                requires_date=requires_date,
                valid_input_ids=valid_input_ids,
                entity_type=entity_type,
                member_state=member_state,
            )
            if finding:
                if include_non_applicable or finding.status != STATUS_NOT_APPLICABLE:
                    findings.append(finding)

        # Invariant 29: Deterministic Deduplication
        deduplicated = cls._deduplicate_findings(findings)

        # Invariant 30: Deterministic stable sorting
        deduplicated.sort(key=lambda f: (f.jurisdiction, f.regulation_id, f.rule_id))

        # Collate all supporting evidence IDs
        all_supporting_ids: Set[str] = set()
        for f in deduplicated:
            all_supporting_ids.update(f.supporting_evidence_ids)

        return RegulatoryCheckResponse(
            findings=deduplicated,
            jurisdiction_resolved=resolved_j,
            jurisdiction_confidence=j_conf,
            supported_rule_registry=supported_rule_registry,
            rule_available=rule_available,
            requires_jurisdiction=requires_jurisdiction,
            requires_date=requires_date,
            supporting_evidence=sorted(all_supporting_ids),
            limitation=limitation,
        )

    @classmethod
    def _evaluate_single_rule(
        cls,
        rule: RegistryRule,
        assessments: List[PatternAssessment],
        resolved_jurisdiction: str,
        jurisdiction_confidence: float,
        is_jurisdiction_match: bool,
        is_jurisdiction_unknown: bool,
        date_applicability: ApplicabilityType,
        date_reason: Optional[str],
        requires_date: bool,
        valid_input_ids: Set[str],
        entity_type: Optional[str] = None,
        member_state: Optional[str] = None,
    ) -> Optional[RegulatoryFinding]:
        """Evaluate a single registry rule against pattern assessments and validity constraints."""
        finding_id = f"REG_{rule.jurisdiction}_{rule.rule_id}"

        def _make_finding(
            status: RegulatoryStatusType,
            applicability: ApplicabilityType,
            confidence: float,
            supporting_eids: List[str],
            supporting_aids: List[str],
            explanation: str,
        ) -> RegulatoryFinding:
            cls._assert_no_forbidden_phrases(explanation)
            return RegulatoryFinding(
                finding_id=finding_id,
                jurisdiction=rule.jurisdiction,
                jurisdiction_confidence=jurisdiction_confidence if not is_jurisdiction_unknown else 0.0,
                regulation_id=rule.regulation_id,
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                pattern=rule.pattern,
                status=status,
                applicability=applicability,
                effective_from=rule.effective_from,
                effective_to=rule.effective_to,
                confidence=confidence,
                supporting_evidence_ids=supporting_eids,
                supporting_assessment_ids=supporting_aids,
                explanation=explanation,
                source=rule.authoritative_source,
                rule_version=rule.version,
                regulated_entity_type=rule.regulated_entity_type,
                service_scope=rule.service_scope,
                requires_entity_scope=rule.requires_entity_scope,
                authority_type=rule.authority_type,
                requires_member_state_mapping=rule.requires_member_state_mapping,
                mapping_type=rule.mapping_type,
            )

        # 1. Jurisdiction Mismatch -> NOT_APPLICABLE
        if not is_jurisdiction_match and not is_jurisdiction_unknown:
            return _make_finding(
                status=STATUS_NOT_APPLICABLE,
                applicability=NOT_APPLICABLE,
                confidence=0.0,
                supporting_eids=[],
                supporting_aids=[],
                explanation=f"Rule applies to jurisdiction {rule.jurisdiction}, but transaction jurisdiction is resolved as {resolved_jurisdiction}.",
            )

        # 2. Unknown Jurisdiction -> UNKNOWN
        if is_jurisdiction_unknown:
            return _make_finding(
                status=STATUS_UNKNOWN,
                applicability=UNKNOWN_APPLICABILITY,
                confidence=0.0,
                supporting_eids=[],
                supporting_aids=[],
                explanation="Transaction jurisdiction is unknown; regulatory applicability cannot be determined without authenticated jurisdiction.",
            )

        # 3. Date Invalidation (predates or expired) -> NOT_APPLICABLE
        if date_applicability == NOT_APPLICABLE:
            return _make_finding(
                status=STATUS_NOT_APPLICABLE,
                applicability=NOT_APPLICABLE,
                confidence=0.0,
                supporting_eids=[],
                supporting_aids=[],
                explanation=f"Regulation is not temporally applicable: {date_reason}",
            )

        # Check for matching assessments
        supported_assessments = [a for a in assessments if a.status == "SUPPORTED"]
        potential_assessments = [a for a in assessments if a.status == "POTENTIAL"]

        # If pattern is completely unobserved or NOT_SUPPORTED
        if not supported_assessments and not potential_assessments:
            return _make_finding(
                status=STATUS_NOT_APPLICABLE,
                applicability=NOT_APPLICABLE,
                confidence=0.0,
                supporting_eids=[],
                supporting_aids=[],
                explanation=f"Available evidence does not support the dark pattern ({rule.pattern}) governed by this rule.",
            )

        # Active assessments present: collect and validate supporting evidence IDs
        matched_assessments = supported_assessments if supported_assessments else potential_assessments
        all_raw_eids: Set[str] = set()
        for a in matched_assessments:
            all_raw_eids.update(a.supporting_evidence_ids)

        # Invariant 12 & 13: Invalidate synthetic or unverified evidence IDs
        has_invalid_ids = bool(all_raw_eids - valid_input_ids) or not all_raw_eids
        verified_eids = sorted(all_raw_eids.intersection(valid_input_ids))

        # Check required conditions for rule
        required_statuses = rule.applicability_conditions.get("pattern_statuses", ["SUPPORTED", "POTENTIAL"])

        # 4. Missing transaction date -> POTENTIALLY_RELEVANT, NEVER SUPPORTED
        if requires_date or date_applicability == UNKNOWN_APPLICABILITY:
            return _make_finding(
                status=STATUS_POTENTIALLY_RELEVANT,
                applicability=UNKNOWN_APPLICABILITY,
                confidence=0.50,
                supporting_eids=verified_eids,
                supporting_aids=[f"{rule.pattern}_assessment"],
                explanation="Potentially relevant regulatory rule detected. Temporal applicability requires transaction date verification.",
            )

        # 5. Entity Scope Validation (P1-03: EU DSA Article 25 applies to ONLINE_PLATFORM)
        if rule.requires_entity_scope and rule.regulated_entity_type:
            norm_entity = entity_type.strip().upper() if entity_type else None
            if norm_entity is None or norm_entity == "UNKNOWN":
                calc_conf = round(min(0.55, 0.85 * jurisdiction_confidence), 2)
                return _make_finding(
                    status=STATUS_POTENTIALLY_RELEVANT,
                    applicability=UNKNOWN_APPLICABILITY,
                    confidence=calc_conf,
                    supporting_eids=verified_eids,
                    supporting_aids=[f"{rule.pattern}_assessment"],
                    explanation=f"Potentially relevant regulatory rule detected. Rule applies to providers of online platforms ({rule.regulated_entity_type}); entity type is unverified so statutory applicability could not be definitively determined.",
                )
            elif norm_entity != rule.regulated_entity_type:
                return _make_finding(
                    status=STATUS_NOT_APPLICABLE,
                    applicability=NOT_APPLICABLE,
                    confidence=0.0,
                    supporting_eids=[],
                    supporting_aids=[],
                    explanation=f"Rule applies to {rule.regulated_entity_type}, but evaluated entity type is {norm_entity}.",
                )

        # 6. EU UCPD Directive / Member State Mapping Validation (P1-04)
        if rule.requires_member_state_mapping:
            norm_ms = member_state.strip().upper() if member_state else None
            if not norm_ms or norm_ms == "UNKNOWN":
                calc_conf = round(min(0.60, 0.85 * jurisdiction_confidence), 2)
                return _make_finding(
                    status=STATUS_POTENTIALLY_RELEVANT,
                    applicability=APPLICABLE,
                    confidence=calc_conf,
                    supporting_eids=verified_eids,
                    supporting_aids=[f"{rule.pattern}_assessment"],
                    explanation="Potentially relevant regulatory rule detected. Directive 2005/29/EC (UCPD) is an EU Directive requiring national Member State transposition; national applicability requires further Member State jurisdiction resolution.",
                )

        # 7. FTC Act Section 5 General Authority (P1-05)
        if rule.authority_type == "GENERAL_CONSUMER_PROTECTION_AUTHORITY" or rule.mapping_type == "POTENTIAL_APPLICABILITY":
            calc_conf = round(min(0.65, 0.75 * jurisdiction_confidence), 2)
            return _make_finding(
                status=STATUS_POTENTIALLY_RELEVANT,
                applicability=APPLICABLE,
                confidence=calc_conf,
                supporting_eids=verified_eids,
                supporting_aids=[f"{rule.pattern}_assessment"],
                explanation="Available evidence may be relevant to the configured Section 5 consumer-protection rule mapping.",
            )

        # 8. Supported pattern with verified date and verified evidence IDs (e.g. IN CCPA, US ROSCA, UK DMCC, or EU DSA with ONLINE_PLATFORM)
        if supported_assessments and "SUPPORTED" in required_statuses:
            if not has_invalid_ids and verified_eids:
                if jurisdiction_confidence >= 0.80:
                    explanation = "Available evidence matches the configured rule conditions for potential regulatory concern."
                    return _make_finding(
                        status=STATUS_SUPPORTED,
                        applicability=APPLICABLE,
                        confidence=0.85,
                        supporting_eids=verified_eids,
                        supporting_aids=[f"{rule.pattern}_assessment"],
                        explanation=explanation,
                    )
                else:
                    calc_conf = round(min(0.65, 0.85 * jurisdiction_confidence), 2)
                    explanation = "Potentially relevant regulatory rule detected. Available evidence matches configured rule conditions, but jurisdiction is inferred from contextual signals rather than authenticated."
                    return _make_finding(
                        status=STATUS_POTENTIALLY_RELEVANT,
                        applicability=APPLICABLE,
                        confidence=calc_conf,
                        supporting_eids=verified_eids,
                        supporting_aids=[f"{rule.pattern}_assessment"],
                        explanation=explanation,
                    )
            else:
                explanation = "Potentially relevant regulatory rule detected. Available evidence indicates potential dark pattern, but supporting evidence provenance could not be fully verified."
                return _make_finding(
                    status=STATUS_POTENTIALLY_RELEVANT,
                    applicability=APPLICABLE,
                    confidence=0.40,
                    supporting_eids=verified_eids,
                    supporting_aids=[f"{rule.pattern}_assessment"],
                    explanation=explanation,
                )

        # 9. Potential pattern match
        if potential_assessments or (supported_assessments and "SUPPORTED" not in required_statuses):
            explanation = "Potentially relevant regulatory rule detected. Available evidence indicates potential dark pattern."
            return _make_finding(
                status=STATUS_POTENTIALLY_RELEVANT,
                applicability=APPLICABLE,
                confidence=0.55,
                supporting_eids=verified_eids,
                supporting_aids=[f"{rule.pattern}_assessment"],
                explanation=explanation,
            )

        return None

    @classmethod
    def _deduplicate_findings(cls, findings: List[RegulatoryFinding]) -> List[RegulatoryFinding]:
        """Deterministically deduplicate findings by (regulation_id, rule_id, jurisdiction)."""
        grouped: Dict[Tuple[str, str, str], RegulatoryFinding] = {}

        for f in findings:
            key = (f.regulation_id, f.rule_id, f.jurisdiction)
            if key not in grouped:
                grouped[key] = f
            else:
                existing = grouped[key]
                # Prioritize higher status severity
                if STATUS_PRIORITY.get(f.status, 0) > STATUS_PRIORITY.get(existing.status, 0):
                    grouped[key] = f
                elif STATUS_PRIORITY.get(f.status, 0) == STATUS_PRIORITY.get(existing.status, 0):
                    # Combine supporting evidence IDs deterministically
                    merged_eids = sorted(set(existing.supporting_evidence_ids + f.supporting_evidence_ids))
                    existing.supporting_evidence_ids = merged_eids
                    existing.confidence = max(existing.confidence, f.confidence)

        return list(grouped.values())

    @staticmethod
    def _assert_no_forbidden_phrases(text: str) -> None:
        """Enforce invariant that legal conclusion language is strictly absent."""
        lower = text.lower()
        for phrase in FORBIDDEN_LEGAL_PHRASES:
            if phrase in lower:
                raise ValueError(f"Forbidden legal conclusion phrase detected in explanation: '{phrase}'")
