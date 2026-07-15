"""Stage 5 — Quality Scorer + Top-50 Selection.

Scores each enriched FO record (0-100) using existing data signals.
Zero additional API queries — purely analytical.

Scoring dimensions (weights sum to 100):
  1. Contact Quality     (30 pts) — email + LinkedIn for best contact
  2. Entity Intelligence (25 pts) — website, crawl depth, investment thesis
  3. Team Discovery      (20 pts) — team members found, source quality
  4. Corporate Presence  (15 pts) — corporate LinkedIn, socials, corporate email
  5. Data Completeness   (10 pts) — how many export fields are populatable

Input:  data/pipeline/03_contacts_enriched.json
Output: data/pipeline/04_scored.json  (all FOs with scores)
        data/pipeline/05_top50.json   (top 50, mapped to export schema)
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Scoring weights ──────────────────────────────────────────────────
W_CONTACT = 30
W_ENTITY = 25
W_TEAM = 20
W_PRESENCE = 15
W_COMPLETENESS = 10


# ── Helper predicates ────────────────────────────────────────────────

PLACEHOLDER_NAMES = {
    "john doe", "jane doe", "full name", "name", "first last",
    "team member", "contact person", "unknown", "n/a",
    "leadership team", "management team", "executive team",
}


def _is_placeholder_contact(name: Optional[str]) -> bool:
    """Check if contact name is a placeholder or company-as-person."""
    if not name:
        return True
    name_lower = name.strip().lower()
    if name_lower in PLACEHOLDER_NAMES:
        return True
    company_indicators = [
        "leadership team", "management team", "executive team",
        "family office", "holdings", " llc", " inc", " ltd",
        " group", " capital", " partners", " management",
        " trust company", " advisors",
    ]
    if any(ind in name_lower for ind in company_indicators):
        return True
    if len(name.strip().split()) < 2:
        return True
    return False


def _has_valid_email(email: Optional[str]) -> bool:
    """Check if string looks like a real email (not placeholder)."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return False
    # Reject obvious placeholders
    placeholder_patterns = [
        "example.com", "test.com", "placeholder", "noreply",
        "no-reply", "donotreply", "email.com",
    ]
    if any(p in email for p in placeholder_patterns):
        return False
    # Reject malformed (stray parens, brackets)
    if re.search(r'[)(}\]{\[\s]', email.split("@")[0]):
        return False
    return True


def _has_valid_linkedin(url: Optional[str]) -> bool:
    """Check if string is a structurally valid LinkedIn profile URL."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip().lower()
    return "linkedin.com/in/" in url and len(url) > 30


def _has_valid_company_linkedin(url: Optional[str]) -> bool:
    """Check if string is a valid LinkedIn company page."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip().lower()
    return "linkedin.com/company/" in url


def _email_confidence_score(email: Optional[str], confidence: Optional[str]) -> float:
    """Score email quality 0-1 based on existence + confidence level."""
    if not _has_valid_email(email):
        return 0.0
    conf = (confidence or "").lower()
    if conf in ("verified", "high"):
        return 1.0
    if conf == "medium":
        return 0.7
    if conf == "low":
        return 0.4
    # Has email but no confidence tag — assume medium
    return 0.5


def _is_senior_title(title: Optional[str]) -> bool:
    """Check if title indicates a senior/decision-maker role."""
    if not title:
        return False
    title_lower = title.lower()
    senior_keywords = [
        "ceo", "cfo", "cio", "coo", "chief", "president", "partner",
        "managing director", "head of", "director", "principal",
        "founder", "chairman", "vp", "vice president", "senior",
    ]
    return any(kw in title_lower for kw in senior_keywords)


# ── Main scorer ──────────────────────────────────────────────────────

def score_family_office(rec: dict) -> dict:
    """Score a single FO record and return it with score breakdown.

    Adds fields:
      - quality_score (0-100)
      - score_breakdown (dict of dimension scores)
      - best_contact_name, best_contact_title, best_contact_email,
        best_contact_linkedin, best_email_confidence, best_email_source
    """
    # ── Pick best contact ────────────────────────────────────────────
    best = _pick_best_contact(rec)

    # ── 1. Contact Quality (0-30) ────────────────────────────────────
    contact_score = 0.0

    # Email sub-score (0-15)
    email_sc = _email_confidence_score(
        best.get("email"), best.get("email_confidence")
    )
    contact_score += email_sc * 15

    # LinkedIn sub-score (0-10)
    if _has_valid_linkedin(best.get("linkedin_url")):
        contact_score += 10

    # Title seniority bonus (0-5)
    if _is_senior_title(best.get("title")):
        contact_score += 5

    # ── 2. Entity Intelligence (0-25) ────────────────────────────────
    entity_score = 0.0

    # Website exists and was crawled (0-8)
    website = rec.get("website") or ""
    crawl_status = (rec.get("crawl_status") or "").lower()
    if website.startswith("http"):
        entity_score += 3
        if crawl_status == "enriched":
            entity_score += 5
        elif crawl_status != "crawlfailed":
            entity_score += 2

    # Investment strategy populated (0-5)
    if rec.get("investment_strategy") and len(str(rec["investment_strategy"])) > 50:
        entity_score += 5

    # AUM data (0-4)
    aum = rec.get("aum") or ""
    if aum and aum not in ("N/A", "Unknown", ""):
        entity_score += 4

    # Headquarters (0-3)
    hq = rec.get("headquarters") or rec.get("location") or ""
    if hq and hq not in ("N/A", "Unknown"):
        entity_score += 3

    # Founded year (0-2)
    if rec.get("founded_year"):
        entity_score += 2

    # Description (0-3)
    desc = rec.get("description") or rec.get("website_description") or ""
    if desc and len(desc) > 30:
        entity_score += 3

    # ── 3. Team Discovery (0-20) ─────────────────────────────────────
    team_score = 0.0
    team = rec.get("team_members") or []
    team_count = len(team)

    # Base: has any team members (0-6)
    if team_count >= 3:
        team_score += 6
    elif team_count >= 1:
        team_score += 3

    # Team members with LinkedIn (0-6)
    li_count = sum(1 for m in team if _has_valid_linkedin(m.get("linkedin_url")))
    if li_count >= 3:
        team_score += 6
    elif li_count >= 1:
        team_score += 3

    # Team members with email (0-5)
    em_count = sum(1 for m in team if _has_valid_email(m.get("email")))
    if em_count >= 2:
        team_score += 5
    elif em_count >= 1:
        team_score += 3

    # Source bonus — website-crawled team > Tavily-discovered (0-3)
    enrichment_tier = rec.get("contact_enrichment_tier")
    if enrichment_tier == 1:
        team_score += 3  # Had team from crawl + filled gaps
    elif enrichment_tier == 2:
        team_score += 2  # Had names from crawl, found contacts
    elif enrichment_tier == 3:
        team_score += 1  # Fully discovered via search

    # ── 4. Corporate Presence (0-15) ─────────────────────────────────
    presence_score = 0.0

    # Corporate LinkedIn (0-6)
    if _has_valid_company_linkedin(rec.get("corporate_linkedin")):
        presence_score += 6

    # Corporate email from crawl (0-4)
    extracted_emails = rec.get("extracted_emails") or []
    if extracted_emails:
        presence_score += 4
    elif rec.get("primary_email") and rec["primary_email"] not in ("null", "", None):
        presence_score += 2

    # Social links (0-3)
    socials = rec.get("social_links") or []
    if len(socials) >= 3:
        presence_score += 3
    elif len(socials) >= 1:
        presence_score += 1

    # LinkedIn profiles from crawl (0-2)
    li_profiles = rec.get("linkedin_profiles") or []
    if len(li_profiles) >= 3:
        presence_score += 2
    elif len(li_profiles) >= 1:
        presence_score += 1

    # ── 5. Data Completeness (0-10) ──────────────────────────────────
    # Count how many of the 28 export columns we can populate
    mappable = _count_mappable_fields(rec, best)
    completeness_score = min(10, round(mappable / 28 * 10, 1))

    # ── Total ────────────────────────────────────────────────────────
    total = round(contact_score + entity_score + team_score +
                  presence_score + completeness_score, 1)

    # Attach scores and best contact to record
    rec["quality_score"] = total
    rec["score_breakdown"] = {
        "contact_quality": round(contact_score, 1),
        "entity_intelligence": round(entity_score, 1),
        "team_discovery": round(team_score, 1),
        "corporate_presence": round(presence_score, 1),
        "data_completeness": round(completeness_score, 1),
    }
    rec["best_contact_name"] = best.get("name")
    rec["best_contact_title"] = best.get("title")
    rec["best_contact_email"] = best.get("email")
    rec["best_contact_linkedin"] = best.get("linkedin_url")
    rec["best_email_confidence"] = best.get("email_confidence", "Not Found")
    rec["best_email_source"] = best.get("email_source")

    return rec


def _pick_best_contact(rec: dict) -> dict:
    """Select the single best contact person from all available data.

    Priority: has email + LinkedIn > has email > has LinkedIn > has title.
    Among ties, prefer senior titles.
    """
    team = rec.get("team_members") or []
    best_contacts = rec.get("best_contacts") or []

    if not team:
        return {}

    # Filter out placeholder contacts before ranking
    real_team = [m for m in team if not _is_placeholder_contact(m.get("name"))]
    if not real_team:
        # All contacts were placeholders — return empty
        return {}

    def _contact_rank(member: dict) -> tuple:
        has_em = 1 if _has_valid_email(member.get("email")) else 0
        has_li = 1 if _has_valid_linkedin(member.get("linkedin_url")) else 0
        is_senior = 1 if _is_senior_title(member.get("title")) else 0
        return (has_em + has_li, has_em, is_senior, has_li)

    ranked = sorted(real_team, key=_contact_rank, reverse=True)
    best = dict(ranked[0])

    # Determine email confidence
    email = best.get("email")
    if _has_valid_email(email):
        # Preserve existing confidence if already set (e.g. from MX verification)
        existing_conf = best.get("email_confidence", "")
        if existing_conf in ("High", "Verified"):
            pass  # Keep the higher confidence
        else:
            contact_source = rec.get("contact_source", "")
            if contact_source == "TavilySearch":
                best["email_confidence"] = "Medium"
                best["email_source"] = best.get("email_source") or "Pattern-inferred via Tavily"
            else:
                best["email_confidence"] = "Medium"
                best["email_source"] = best.get("email_source") or "Discovered"
    else:
        # Try extracted_emails from website crawl as fallback
        extracted = rec.get("extracted_emails") or []
        if extracted:
            best["email"] = extracted[0]
            best["email_confidence"] = "Low"
            best["email_source"] = "Website crawl (generic)"
        else:
            best["email_confidence"] = "Not Found"
            best["email_source"] = None

    return best


def _count_mappable_fields(rec: dict, best_contact: dict) -> int:
    """Count how many of the 28 export schema fields can be populated."""
    count = 0

    # Tier 1 fields
    if rec.get("name"):
        count += 1
    if rec.get("type") or rec.get("firm_type"):
        count += 1
    if rec.get("description") or rec.get("website_description"):
        count += 1
    if rec.get("founded_year"):
        count += 1
    if rec.get("aum"):
        count += 1
    if rec.get("source"):
        count += 1  # aum_source
    if rec.get("investment_strategy") or rec.get("website_investment_thesis"):
        count += 1
    if rec.get("sectors") or rec.get("asset_classes"):
        count += 1
    if rec.get("website"):
        count += 1
    if rec.get("website"):
        count += 1  # url_quality (derived)
    if rec.get("corporate_linkedin"):
        count += 1
    extracted = rec.get("extracted_emails") or []
    if extracted:
        count += 1  # corporate_email
    if rec.get("social_links"):
        count += 1
    # HQ parsing
    hq = rec.get("headquarters") or rec.get("location") or ""
    if hq:
        count += 1  # at least city
        if "," in hq:
            count += 1  # state
            if hq.count(",") >= 2 or "United States" in hq:
                count += 1  # country

    # Tier 2 fields
    if best_contact.get("name"):
        count += 1
    if best_contact.get("title"):
        count += 1
    if _has_valid_linkedin(best_contact.get("linkedin_url")):
        count += 1
    if _has_valid_email(best_contact.get("email")):
        count += 1
    count += 1  # email_confidence always populated
    count += 1  # email_source always populated

    # Tier 3 fields
    activity = rec.get("recent_activity") or {}
    if isinstance(activity, dict) and activity.get("title"):
        count += 1
    if isinstance(activity, dict) and activity.get("date"):
        count += 1
    if isinstance(activity, dict) and activity.get("url"):
        count += 1
    holdings = rec.get("notable_holdings") or rec.get("key_investments") or []
    if holdings:
        count += 1

    # Tier 4 — always populated
    count += 2  # completeness + confidence

    return count


# ── Field mapping (enriched JSON → 28-col export schema) ─────────────

def map_to_export_schema(rec: dict) -> dict:
    """Map an enriched+scored FO record to the 28-column export schema."""
    out = {}

    # ── Tier 1: Entity Core ──────────────────────────────────────────
    raw_name = (rec.get("name") or "Unknown").strip()
    # Strip trailing " Family Office" suffix only (not mid-string)
    if raw_name.endswith(" Family Office"):
        raw_name = raw_name[: -len(" Family Office")].strip()
    # Handle double suffix: "Mars Family Office Family Office"
    if raw_name.endswith(" Family Office"):
        raw_name = raw_name[: -len(" Family Office")].strip()
    out["family_office_name"] = raw_name or rec.get("name", "Unknown")

    # Entity type
    firm_type = rec.get("firm_type") or rec.get("type") or "Unknown"
    if firm_type in ("Single Family Office", "Multi Family Office", "Hybrid"):
        out["entity_type"] = firm_type
    elif "multi" in firm_type.lower() or "mfo" in firm_type.lower():
        out["entity_type"] = "Multi Family Office"
    elif "single" in firm_type.lower() or "sfo" in firm_type.lower():
        out["entity_type"] = "Single Family Office"
    elif "hybrid" in firm_type.lower():
        out["entity_type"] = "Hybrid"
    else:
        out["entity_type"] = "Unknown"

    out["description"] = rec.get("website_description") or rec.get("description")
    out["year_founded"] = str(rec["founded_year"]) if rec.get("founded_year") else None
    out["aum_estimated"] = rec.get("aum")
    out["aum_source"] = rec.get("aum_date") or rec.get("source") or "PipelineRoad"

    out["investment_thesis"] = (
        rec.get("website_investment_thesis")
        or (rec.get("investment_strategy") or "")[:300] or None
    )

    # Sectors
    sectors = rec.get("sectors") or rec.get("asset_classes") or []
    out["investing_sectors"] = ", ".join(sectors) if sectors else None

    # Website + quality
    website = rec.get("website") or ""
    out["website_url"] = website if website.startswith("http") else None
    crawl = (rec.get("crawl_status") or "").lower()
    if not website:
        out["url_quality"] = "Not Found"
    elif crawl == "enriched":
        out["url_quality"] = "Highest"
    elif crawl == "crawlfailed":
        out["url_quality"] = "Medium-Low"
    else:
        out["url_quality"] = "Medium"

    out["corporate_linkedin_url"] = rec.get("corporate_linkedin")

    # Corporate email
    extracted = rec.get("extracted_emails") or []
    if extracted:
        out["corporate_email"] = extracted[0]
    elif rec.get("primary_email") and rec["primary_email"] not in ("null", ""):
        out["corporate_email"] = rec["primary_email"]
    else:
        out["corporate_email"] = None

    # Other socials
    socials = rec.get("social_links") or []
    # Filter out share/intent links
    real_socials = [
        s for s in socials
        if "intent/" not in s and "sharer/" not in s
    ]
    out["other_socials"] = " | ".join(real_socials[:5]) if real_socials else None

    # HQ parsing — use _resolved_country from enrichment_boost if available
    hq = rec.get("headquarters") or rec.get("location") or ""
    hq_parts = [p.strip() for p in hq.split(",")]
    out["hq_city"] = hq_parts[0] if len(hq_parts) >= 1 and hq_parts[0] else None
    out["hq_state"] = hq_parts[1] if len(hq_parts) >= 2 else None

    # Country: prefer resolved (from enrichment_boost), then explicit 3rd part, then smart default
    resolved_country = rec.get("_resolved_country")
    if resolved_country:
        out["hq_country"] = resolved_country
    elif len(hq_parts) >= 3 and hq_parts[2]:
        out["hq_country"] = hq_parts[2]
    else:
        # Only default to US if location looks domestic (has US state abbreviation or "United States")
        state = (out.get("hq_state") or "").strip()
        us_states = {
            "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
            "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
            "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
            "TX","UT","VT","VA","WA","WV","WI","WY","DC",
            "Alabama","Alaska","Arizona","Arkansas","California","Colorado",
            "Connecticut","Delaware","Florida","Georgia","Hawaii","Idaho","Illinois",
            "Indiana","Iowa","Kansas","Kentucky","Louisiana","Maine","Maryland",
            "Massachusetts","Michigan","Minnesota","Mississippi","Missouri","Montana",
            "Nebraska","Nevada","New Hampshire","New Jersey","New Mexico","New York",
            "North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania",
            "Rhode Island","South Carolina","South Dakota","Tennessee","Texas","Utah",
            "Vermont","Virginia","Washington","West Virginia","Wisconsin","Wyoming",
        }
        if state in us_states or "united states" in hq.lower():
            out["hq_country"] = "United States"
        else:
            out["hq_country"] = None  # Don't assume US for ambiguous locations

    # ── Tier 2: Principal Intelligence ────────────────────────────────
    out["contact_name"] = rec.get("best_contact_name")
    out["contact_title"] = rec.get("best_contact_title")
    out["contact_linkedin"] = rec.get("best_contact_linkedin")
    out["contact_email"] = rec.get("best_contact_email")
    out["email_confidence"] = rec.get("best_email_confidence", "Not Found")
    out["email_source"] = rec.get("best_email_source")

    # ── Tier 3: Entity Signals ────────────────────────────────────────
    activity = rec.get("recent_activity") or {}
    if isinstance(activity, dict):
        out["recent_activity"] = activity.get("title") or activity.get("summary")
        out["activity_date"] = activity.get("date")
        out["activity_source_url"] = activity.get("url")
    else:
        out["recent_activity"] = None
        out["activity_date"] = None
        out["activity_source_url"] = None

    holdings = rec.get("notable_holdings") or []
    if isinstance(holdings, list) and holdings:
        out["key_investments"] = ", ".join(str(h) for h in holdings[:8])
    else:
        out["key_investments"] = None

    # ── Tier 4: Data Quality ──────────────────────────────────────────
    out["confidence_score"] = rec.get("quality_score", 0)
    # data_completeness_score recalculated by validator._clean_record()
    out["data_completeness_score"] = None

    return out


def score_and_rank(records: list[dict], top_n: int = 50) -> tuple[list[dict], list[dict]]:
    """Score all records, rank by quality_score, return (all_scored, top_n_export).

    Returns:
        all_scored: All FO records with quality_score + breakdown attached
        top_export: Top N records mapped to the 28-column export schema
    """
    logger.info(f"Scoring {len(records)} family offices...")

    # Score each record
    scored = []
    for rec in records:
        scored_rec = score_family_office(rec)
        scored.append(scored_rec)

    # Sort by quality_score descending
    scored.sort(key=lambda r: r.get("quality_score", 0), reverse=True)

    # Log score distribution
    scores = [r["quality_score"] for r in scored]
    if scores:
        avg = sum(scores) / len(scores)
        top_score = scores[0]
        bottom_score = scores[-1]
        median = scores[len(scores) // 2]
        logger.info(f"  Score range: {bottom_score} – {top_score}")
        logger.info(f"  Average: {avg:.1f} | Median: {median}")

    # Select top N
    top = scored[:top_n]
    logger.info(f"  Selected top {len(top)} (cutoff score: {top[-1]['quality_score'] if top else 0})")

    # Map to export schema
    top_export = [map_to_export_schema(r) for r in top]

    return scored, top_export
