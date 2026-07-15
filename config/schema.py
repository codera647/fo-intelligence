"""30-column Family Office schema — Pydantic models + constants."""

from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


# ── enums ──────────────────────────────────────────────────────────
class EntityType(str, Enum):
    SFO = "Single Family Office"
    MFO = "Multi Family Office"
    HYBRID = "Hybrid"
    UNKNOWN = "Unknown"


class UrlQuality(str, Enum):
    HIGHEST = "Highest"
    MEDIUM = "Medium"
    MEDIUM_LOW = "Medium-Low"
    LOWER = "Lower"
    NOT_FOUND = "Not Found"


class EmailConfidence(str, Enum):
    VERIFIED = "Verified"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    NOT_FOUND = "Not Found"


# ── main schema ────────────────────────────────────────────────────
class FamilyOfficeRecord(BaseModel):
    """One row in the final 50-record dataset — 30 columns across 4 tiers."""

    # ── Tier 1: Entity Core (18) ───────────────────────────────────
    family_office_name: str = Field(..., description="Official entity name")
    entity_type: str = Field(default="Unknown", description="SFO / MFO / Hybrid")
    description: Optional[str] = Field(None, description="1-2 sentence summary")
    year_founded: Optional[str] = Field(None, description="Year established")
    aum_estimated: Optional[str] = Field(None, description="Assets Under Management estimate")
    aum_source: Optional[str] = Field(None, description="Where AUM figure was sourced")
    investment_thesis: Optional[str] = Field(None, description="Core investment philosophy")
    investing_sectors: Optional[str] = Field(None, description="Comma-separated sectors")
    website_url: Optional[str] = Field(None, description="Primary website")
    url_quality: str = Field(default="Not Found", description="Highest/Medium/Medium-Low/Lower/Not Found")
    corporate_linkedin: Optional[str] = Field(None, description="Company LinkedIn page")
    linkedin_source: Optional[str] = Field(None, description="How LinkedIn URL was found")
    corporate_email: Optional[str] = Field(None, description="Company email (info@, contact@, etc.)")
    corp_email_source: Optional[str] = Field(None, description="How corporate email was found")
    other_socials: Optional[str] = Field(None, description="Twitter, Instagram, Facebook URLs (pipe-separated)")
    hq_city: Optional[str] = Field(None, description="Headquarters city")
    hq_state: Optional[str] = Field(None, description="Headquarters state/province")
    hq_country: Optional[str] = Field(None, description="Headquarters country")

    # ── Tier 2: Principal Intelligence (6) ─────────────────────────
    contact_name: Optional[str] = Field(None, description="Key decision-maker name")
    contact_title: Optional[str] = Field(None, description="Title/role")
    contact_linkedin: Optional[str] = Field(None, description="Personal LinkedIn URL")
    contact_email: Optional[str] = Field(None, description="Email address")
    email_confidence: str = Field(default="Not Found", description="Verified/High/Medium/Low/Not Found")
    email_source: Optional[str] = Field(None, description="How email was found/verified")

    # ── Tier 3: Entity Signals (4) ─────────────────────────────────
    recent_activity: Optional[str] = Field(None, description="Latest news/activity")
    activity_date: Optional[str] = Field(None, description="Date of activity")
    activity_source_url: Optional[str] = Field(None, description="Source link for activity")
    key_investments: Optional[str] = Field(None, description="Notable portfolio companies/deals")

    # ── Tier 4: Data Quality (2) ───────────────────────────────────
    data_completeness_score: Optional[float] = Field(None, description="% of non-null columns (0-100)")
    confidence_score: Optional[float] = Field(None, description="Overall verification confidence (0-100)")


# ── column list (for export ordering) ─────────────────────────────
COLUMN_ORDER: List[str] = [
    # Tier 1
    "family_office_name", "entity_type", "description", "year_founded",
    "aum_estimated", "aum_source", "investment_thesis", "investing_sectors",
    "website_url", "url_quality", "corporate_linkedin", "linkedin_source",
    "corporate_email", "corp_email_source", "other_socials",
    "hq_city", "hq_state", "hq_country",
    # Tier 2
    "contact_name", "contact_title", "contact_linkedin", "contact_email",
    "email_confidence", "email_source",
    # Tier 3
    "recent_activity", "activity_date", "activity_source_url", "key_investments",
    # Tier 4
    "data_completeness_score", "confidence_score",
]

# Top 20 Investment Sectors (from sample dataset taxonomy)
INVESTMENT_SECTORS = [
    "Technology", "Healthcare", "Real Estate", "Energy",
    "Financial Services", "Consumer", "Industrials", "Infrastructure",
    "Agriculture", "Education", "Media & Entertainment", "Biotech",
    "Clean Energy", "Artificial Intelligence", "Cybersecurity",
    "Fintech", "SaaS", "E-commerce", "Aerospace & Defense", "Logistics"
]
