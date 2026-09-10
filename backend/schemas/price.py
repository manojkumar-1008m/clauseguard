"""backend/schemas/price.py
Pydantic models for ClauseGuard Price & Cost Analyzer.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, validator


class PriceAnalysisRequest(BaseModel):
    text: str = Field(..., description="The text to analyze for monetary entities")

    @validator("text")
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("`text` must be a non-empty string")
        if len(v) > 5000:
            raise ValueError("`text` exceeds maximum allowed length (5000 characters)")
        return v


class PriceEntity(BaseModel):
    amount: float = Field(..., description="Normalized monetary amount")
    currency: Optional[str] = Field(default=None, description="Normalized currency code (INR, USD, EUR, GBP)")
    original_text: str = Field(..., description="Exact substring matched in original text")
    context: str = Field(..., description="Surrounding sentence or text context")
    type: str = Field(default="unknown", description="Cost type classification (e.g. base_price, processing_fee, total_price, trial_price, renewal_price, subscription_price, initial_price, previous_price, current_price)")
    relationship_type: Optional[str] = Field(default=None, description="Semantic relationship to other costs (e.g. additional_cost, final_total, alternative, trial_offer, renews_from, recurring_cost, price_change_to, price_change_from)")
    related_entity_index: Optional[int] = Field(default=None, description="Index of related entity in the entities list, if applicable")
    billing_period: Optional[str] = Field(default=None, description="Normalized billing period: day, week, month, year")
    recurring: bool = Field(default=False, description="Whether this price entity is recurring")
    character_start: Optional[int] = Field(default=None, description="Character start offset in original text")
    character_end: Optional[int] = Field(default=None, description="Character end offset in original text")
    entity_index: Optional[int] = Field(default=None, description="Order index of entity in extracted list")
    position_start: Optional[int] = Field(default=None, description="Character start offset in original text (alias for character_start)")
    position_end: Optional[int] = Field(default=None, description="Character end offset in original text (alias for character_end)")
    sentence_index: Optional[int] = Field(default=None, description="0-based sentence index where entity appears")
    disclosure_order: Optional[int] = Field(default=None, description="0-based disclosure order of entity in text (alias for entity_index)")


class DisplayedPrice(BaseModel):
    amount: float = Field(..., description="Base or displayed monetary amount")
    currency: str = Field(..., description="Currency code of the displayed price")


class PriceAnalysisResponse(BaseModel):
    source: str = Field(default="price", description="Source analyzer identifier")
    entities: List[PriceEntity] = Field(default_factory=list, description="List of detected monetary entities")
    displayed_price: Optional[DisplayedPrice] = Field(default=None, description="Primary displayed or base price")
    additional_costs: Optional[float] = Field(default=None, description="Sum of explicit additional costs (fees, taxes, etc.)")
    additional_cost: Optional[float] = Field(default=None, description="Alias for additional_costs")
    explicit_total: Optional[float] = Field(default=None, description="Authoritative total stated explicitly in text")
    calculated_subtotal: Optional[float] = Field(default=None, description="Computed sum of base price and additional costs")
    known_total: Optional[float] = Field(default=None, description="Authoritative or computed known total price")
    total_source: Optional[str] = Field(default=None, description="Source of known total: 'explicit' or 'computed'")
    price_difference: Optional[float] = Field(default=None, description="Numeric difference (e.g. additional fees, discount amount, or renewal increase)")
    additional_cost_percentage: Optional[float] = Field(default=None, description="Percentage of additional cost relative to base price")
    discount_amount: Optional[float] = Field(default=None, description="Calculated or stated discount amount")
    discount_percentage: Optional[float] = Field(default=None, description="Percentage savings relative to original price")
    is_alternative_pricing: bool = Field(default=False, description="Whether entities represent mutually exclusive alternative options")

    # Phase 8.4: Trial, Renewal & Recurring Cost fields
    trial_price: Optional[float] = Field(default=None, description="Explicit trial price (0 for free trial)")
    trial_currency: Optional[str] = Field(default=None, description="Currency code for trial price")
    trial_duration_days: Optional[int] = Field(default=None, description="Duration of trial period in days")
    initial_price: Optional[float] = Field(default=None, description="Initial or promotional period price")
    initial_currency: Optional[str] = Field(default=None, description="Currency code for initial price")
    later_price: Optional[float] = Field(default=None, description="Alias for renewal/later price")
    renewal_price: Optional[float] = Field(default=None, description="Renewal or subsequent recurring price")
    renewal_currency: Optional[str] = Field(default=None, description="Currency code for renewal price")
    currency: Optional[str] = Field(default=None, description="Primary or unambiguous currency code")
    billing_period: Optional[str] = Field(default=None, description="Normalized billing period: day, week, month, year")
    recurring: bool = Field(default=False, description="Whether recurring billing applies")
    promotion_duration_days: Optional[int] = Field(default=None, description="Duration of promotional period in days")
    promotion_duration_months: Optional[int] = Field(default=None, description="Duration of promotional period in months")
    price_change_percentage: Optional[float] = Field(default=None, description="Percentage change from initial to renewal price, or price change percentage")

    # Phase 8.5: Late-disclosure & Price-Change Detection fields
    previous_price: Optional[float] = Field(default=None, description="Explicitly stated former/previous price")
    previous_currency: Optional[str] = Field(default=None, description="Currency code of former/previous price")
    current_price: Optional[float] = Field(default=None, description="Explicitly stated new/current/later price")
    current_currency: Optional[str] = Field(default=None, description="Currency code of new/current/later price")
    price_change: Optional[float] = Field(default=None, description="Numeric difference: current_price - previous_price")
    price_change_detected: bool = Field(default=False, description="Whether an explicit price change was detected")
    price_changed: bool = Field(default=False, description="Alias indicating whether a price change was detected")
    price_change_direction: Optional[str] = Field(default=None, description="Direction of price change: 'increase', 'decrease', or None")
    late_disclosed: Optional[bool] = Field(default=None, description="Whether an additional fee was disclosed after an initial/displayed price")
    late_disclosure_detected: bool = Field(default=False, description="Whether an additional fee was disclosed after an initial price")
    additional_cost_detected: bool = Field(default=False, description="Whether an additional fee or cost was detected")
    renewal_price_detected: bool = Field(default=False, description="Whether a renewal price was detected")
    initial_price_position: Optional[int] = Field(default=None, description="Character start position of initial/displayed price in text")
    additional_cost_position: Optional[int] = Field(default=None, description="Character start position of additional fee in text")


