"""Enrichment pipeline — takes raw candidates, fills 28 columns per record.

Orchestration:
  1. Website scraping (multi-page BFS) → structured extraction (contacts, emails, socials)
  1b. FO classification (OpenRouter + Claude 3.5 Haiku)
  2. SEC EDGAR enrichment (address, filings, AUM, sectors)
  3. ProPublica enrichment (foundation officers, assets, address)
  4. LLM enhancement (description, thesis, sectors, entity_type ONLY)
  5. AUM web search fallback
  6. Corporate LinkedIn (from scrape → Brave fallback, no fake slugs)
  7. Contact validation (LinkedIn via Brave Search, email via MailScout)
  8-11. Quality scores + normalization

Key principle: ALL contacts, emails, LinkedIn URLs come from structured extraction
or validated search — NEVER from LLM generation.
"""

import re
import time
import logging
from typing import List, Dict, Optional
from tqdm import tqdm

from config.schema import FamilyOfficeRecord, COLUMN_ORDER
from config.settings import REQUEST_DELAY
from .website_scraper import scrape_website, check_url_status
from .llm_extractor import extract_from_website, enrich_with_llm
from .edgar_enrichment import enrich_from_edgar
from .propublica_enrichment import enrich_from_propublica
from .contact_validator import validate_contact
from .fo_classifier import classify_entity
from ..discovery.web_search import search_for_website

logger = logging.getLogger(__name__)

# Fields that LLM is ALLOWED to enhance
LLM_ALLOWED_FIELDS = {
    "description", "investment_thesis", "investing_sectors", "entity_type",
    "year_founded", "hq_city", "hq_state", "hq_country",
    "contact_name", "contact_title",
}


def run_enrichment(
    candidates: List[Dict],
    target: int = 55,
    on_record_complete=None,
) -> List[Dict]:
    """Enrich candidates to fill 28-column schema.

    Args:
        candidates: Raw discovery candidates.
        target: Number of enriched records to aim for.
        on_record_complete: Optional callback(record, all_enriched_so_far)
            called after each viable record is added.  Use this for
            incremental saving so data is never lost on a crash.
    """
    enriched_records = []
    logger.info(f"Starting enrichment for {len(candidates)} candidates (target: {target})")

    for i, candidate in enumerate(tqdm(candidates, desc="Enriching")):
        if len(enriched_records) >= target:
            break
        try:
            record = _enrich_single(candidate)
            if record and _is_viable_record(record):
                enriched_records.append(record)
                completeness = record.get("data_completeness_score", 0)
                logger.info(
                    f"  [{len(enriched_records)}/{target}] {record.get('family_office_name')} "
                    f"— {completeness}% complete"
                )
                # Incremental save callback
                if on_record_complete:
                    try:
                        on_record_complete(record, enriched_records)
                    except Exception as cb_err:
                        logger.warning(f"  Incremental save failed: {cb_err}")
            else:
                logger.debug(f"  Skipped (too sparse): {candidate.get('name')}")
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.warning(f"  Error enriching {candidate.get('name')}: {e}")
            continue

    logger.info(f"Enrichment complete: {len(enriched_records)} viable records")
    return enriched_records


def _enrich_single(candidate: Dict) -> Optional[Dict]:
    """Enrich a single candidate through all channels."""
    name = candidate.get("name", "")
    if not name:
        return None

    record = {
        "family_office_name": name,
        "entity_type": candidate.get("entity_type", "Unknown"),
    }

    for field in ["hq_city", "hq_state", "hq_country", "description"]:
        if candidate.get(field):
            record[field] = candidate[field]

    # ── Step 1: Website scraping + LLM extraction ──────────────────
    website_url = candidate.get("website")
    content = None  # Preserve scraper output for team member parsing in Step 7

    if not website_url:
        website_url = search_for_website(name)
        time.sleep(0.5)

    if website_url:
        record["website_url"] = website_url
        record["url_quality"] = check_url_status(website_url)

        content = scrape_website(website_url)
        if content:
            extracted = extract_from_website(website_url, content)
            if extracted:
                for key, value in extracted.items():
                    if value and key in COLUMN_ORDER and not record.get(key):
                        record[key] = value
            time.sleep(0.5)
    else:
        record["url_quality"] = "Not Found"

    # ── Step 1b: FO Classification (OpenRouter + Claude 3.5 Haiku) ───
    classification = classify_entity(
        name=name,
        website_content=content,
        notes=candidate.get("notes", ""),
    )
    if not classification["is_family_office"]:
        logger.info(f"  REJECTED (not a family office): {name} — {classification['reasoning']}")
        return None
    # Use classifier's entity_type if current is Unknown
    if classification.get("entity_type") and classification["entity_type"] not in ("Unknown", "Not a Family Office"):
        if not record.get("entity_type") or record["entity_type"] == "Unknown":
            record["entity_type"] = classification["entity_type"]

    # ── Step 2: SEC EDGAR enrichment ─────────────────────────────────
    try:
        cik = candidate.get("cik")
        edgar_data = enrich_from_edgar(name, record, cik=cik)
        if edgar_data:
            for key, value in edgar_data.items():
                if value and key in COLUMN_ORDER and not record.get(key):
                    record[key] = value
    except Exception as e:
        logger.debug(f"EDGAR enrichment skipped for {name}: {e}")
    time.sleep(0.3)

    # ── Step 3: ProPublica enrichment ─────────────────────────────
    try:
        propublica_data = enrich_from_propublica(name, record)
        if propublica_data:
            for key, value in propublica_data.items():
                if value and key in COLUMN_ORDER and not record.get(key):
                    record[key] = value
    except Exception as e:
        logger.debug(f"ProPublica enrichment skipped for {name}: {e}")
    time.sleep(0.3)

    # ── Step 4: LLM enhancement (RESTRICTED to allowed fields) ────
    pre_llm_fields = {k for k, v in record.items() if v}

    llm_data = enrich_with_llm(name, record)
    if llm_data:
        for key, value in llm_data.items():
            if key in LLM_ALLOWED_FIELDS and value and key in COLUMN_ORDER and not record.get(key):
                record[key] = value
            elif key not in LLM_ALLOWED_FIELDS and value:
                logger.debug(f"  Blocked LLM field '{key}' for {name} (not in allowed set)")

    # ── Step 4b: LLM trust guardrails (extra safety layer) ────────
    _apply_llm_guardrails(record, pre_llm_fields)
    time.sleep(0.3)

    # ── Step 5: AUM web search fallback ──────────────────────────
    if not record.get("aum_estimated"):
        aum_result = _search_aum_web(name)
        if aum_result:
            record["aum_estimated"] = aum_result["aum"]
            record["aum_source"] = aum_result["source"]
        time.sleep(0.5)

    # ── Step 6: Corporate LinkedIn, Email, Socials (from scrape markers) ─
    if content:
        # Corporate LinkedIn — prefer scraped, Brave fallback, NEVER fake slug
        if not record.get("corporate_linkedin_url"):
            scraped_li = _parse_marker(content, "CORPORATE_LINKEDIN")
            if scraped_li:
                record["corporate_linkedin_url"] = scraped_li
            else:
                record["corporate_linkedin_url"] = _search_corporate_linkedin(name)

        # Corporate email — from scrape
        if not record.get("corporate_email"):
            corp_email = _parse_marker(content, "CORPORATE_EMAIL")
            if corp_email:
                record["corporate_email"] = corp_email

        # Other socials — from scrape
        if not record.get("other_socials"):
            socials_raw = _parse_marker(content, "OTHER_SOCIALS")
            if socials_raw:
                record["other_socials"] = " | ".join(socials_raw.strip().split("\n"))
    else:
        # No website content — try Brave for corporate LinkedIn only
        if not record.get("corporate_linkedin_url"):
            record["corporate_linkedin_url"] = _search_corporate_linkedin(name)

    # ── Step 7: Contact validation (smart selection + LinkedIn + email) ─
    team_members = _parse_team_members_from_content(content) if content else []
    known_emails = _parse_emails_from_content(content) if content else []

    if record.get("contact_email") and record["contact_email"] not in known_emails:
        known_emails.append(record["contact_email"])

    contact_name = record.get("contact_name")

    validation = validate_contact(
        contact_name=contact_name or "",
        company_name=name,
        website_url=record.get("website_url"),
        known_emails=known_emails if known_emails else None,
        team_members=team_members if team_members else None,
    )

    # Apply contact name (may have been upgraded by smart selection)
    if validation.get("contact_name") and validation["contact_name"] not in ("", "unknown", "n/a"):
        if not contact_name or contact_name.lower() in ("unknown", "n/a", "none"):
            record["contact_name"] = validation["contact_name"]
        elif validation["contact_name"] != contact_name:
            record["contact_name"] = validation["contact_name"]

    if validation.get("contact_title") and not record.get("contact_title"):
        record["contact_title"] = validation["contact_title"]

    if validation.get("contact_linkedin") and not record.get("contact_linkedin"):
        record["contact_linkedin"] = validation["contact_linkedin"]

    if validation.get("contact_email"):
        if not record.get("contact_email") or validation["email_confidence"] in ("Verified", "High"):
            record["contact_email"] = validation["contact_email"]
            record["email_confidence"] = validation["email_confidence"]
            record["email_source"] = validation["email_source"]

    time.sleep(0.3)

    # ── Step 8: Set email confidence for website-scraped emails ───
    if record.get("contact_email") and not record.get("email_confidence"):
        if record.get("url_quality") == "Highest":
            record["email_confidence"] = "High"
        else:
            record["email_confidence"] = "Medium"
        record["email_source"] = record.get("email_source") or "Website scrape"
    elif not record.get("contact_email"):
        record["email_confidence"] = "Not Found"

    # ── Step 9: Ensure entity_type is set ─────────────────────────
    if not record.get("entity_type") or record["entity_type"] == "Unknown":
        record["entity_type"] = _infer_entity_type(name, record)

    # ── Step 10: Normalize country names ──────────────────────────
    if record.get("hq_country"):
        record["hq_country"] = _normalize_country(record["hq_country"])

    # ── Step 11: Compute quality scores ───────────────────────────
    record["data_completeness_score"] = _compute_completeness(record)
    record["confidence_score"] = _compute_confidence(record, candidate)

    return record


def _is_viable_record(record: Dict) -> bool:
    """A record is viable if it has enough data to be actionable."""
    filled = sum(
        1 for k in COLUMN_ORDER
        if record.get(k)
        and k != "family_office_name"
        and str(record[k]).lower() not in ("unknown", "not found", "none")
    )
    return filled >= 5


def _apply_llm_guardrails(record: Dict, pre_llm_fields: set) -> None:
    """Strip LLM-generated fields that are high-risk for hallucination."""
    STRIP_IF_LLM = ["contact_email"]

    for field in STRIP_IF_LLM:
        if field not in pre_llm_fields and record.get(field):
            logger.debug(f"  Stripped LLM-generated {field} for {record.get('family_office_name')}")
            record[field] = None

    if "contact_linkedin" not in pre_llm_fields and record.get("contact_linkedin"):
        logger.debug(f"  Stripped LLM-generated contact_linkedin for {record.get('family_office_name')}")
        record["contact_linkedin"] = None

    if "aum_estimated" not in pre_llm_fields and record.get("aum_estimated"):
        logger.debug(f"  Stripped LLM-generated AUM for {record.get('family_office_name')}")
        record["aum_estimated"] = None
        record["aum_source"] = None

    if "contact_email" in pre_llm_fields and record.get("contact_email"):
        email = record["contact_email"]
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            record["contact_email"] = None
            record["email_confidence"] = "Not Found"


def _parse_marker(content: str, marker_name: str) -> Optional[str]:
    """Parse a single-value or multi-line marker from scraper output.

    Returns the text between === MARKER_NAME === and the next === or EOF.
    """
    if not content:
        return None
    marker = f"=== {marker_name} ==="
    if marker not in content:
        return None
    try:
        idx = content.index(marker)
        section = content[idx + len(marker):]
        end_idx = section.find("\n===")
        if end_idx > 0:
            section = section[:end_idx]
        result = section.strip()
        return result if result else None
    except (ValueError, IndexError):
        return None


def _search_corporate_linkedin(name: str) -> Optional[str]:
    """Search Brave for company LinkedIn page. Returns verified URL or None.

    Never generates fake slugs — returns None if not found.
    """
    from ..discovery.web_search import _brave_search

    query = f'"{name}" site:linkedin.com/company/'
    try:
        results = _brave_search(query, max_results=5)
        for r in results:
            url = r.get("url", "")
            if "linkedin.com/company/" not in url.lower():
                continue

            # Verify: result title/text must mention a distinctive word from the name
            title = r.get("title", "")
            text = r.get("text", "")
            combined = f"{title} {text}".lower()
            name_words = [w.lower() for w in name.split() if len(w) > 3]
            distinctive = [w for w in name_words if w not in {
                "family", "office", "capital", "investment", "investments",
                "group", "management", "partners", "wealth", "holdings",
                "advisors", "advisory", "fund", "trust", "the",
            }]
            # Need at least one distinctive word match, or last-name match
            if distinctive and any(w in combined for w in distinctive):
                clean = url.split("?")[0].rstrip("/") + "/"
                logger.debug(f"Verified corporate LinkedIn for {name}: {clean}")
                return clean
            # If no distinctive words (common for FOs), check if all short name words match
            elif not distinctive and name_words and all(w in combined for w in name_words[:2]):
                clean = url.split("?")[0].rstrip("/") + "/"
                return clean

    except Exception as e:
        logger.debug(f"Corporate LinkedIn search failed for '{name}': {e}")

    return None


def _infer_entity_type(name: str, record: Dict) -> str:
    """Infer entity type from name and description."""
    name_lower = name.lower()
    desc = (record.get("description") or "").lower()
    combined = name_lower + " " + desc
    if "multi family" in combined or "multi-family" in combined:
        return "Multi Family Office"
    if "single family" in combined or "family office" in combined:
        return "Single Family Office"
    if any(w in combined for w in ["wealth management", "wealth advisory", "private wealth"]):
        return "Multi Family Office"
    if any(w in combined for w in ["family", "personal", "private investment"]):
        return "Single Family Office"
    return "Single Family Office"


def _normalize_country(country: str) -> str:
    """Normalize country names to full form."""
    mapping = {
        "us": "United States of America",
        "usa": "United States of America",
        "united states": "United States of America",
        "u.s.": "United States of America",
        "u.s.a.": "United States of America",
        "uk": "United Kingdom",
        "u.k.": "United Kingdom",
        "uae": "United Arab Emirates",
        "singapore": "Singapore",
        "switzerland": "Switzerland",
        "germany": "Germany",
        "france": "France",
        "canada": "Canada",
        "australia": "Australia",
        "hong kong": "Hong Kong",
        "india": "India",
        "japan": "Japan",
        "china": "China",
        "brazil": "Brazil",
        "israel": "Israel",
        "netherlands": "Netherlands",
        "sweden": "Sweden",
        "norway": "Norway",
    }
    return mapping.get(country.lower().strip(), country)


def _compute_completeness(record: Dict) -> float:
    """Calculate data completeness score (0-100)."""
    core_fields = [
        "family_office_name", "entity_type", "description", "investment_thesis",
        "investing_sectors", "website_url", "hq_city", "hq_country",
        "contact_name", "contact_title",
    ]
    secondary_fields = [
        "year_founded", "aum_estimated", "corporate_linkedin_url",
        "corporate_email", "other_socials",
        "hq_state", "contact_linkedin", "contact_email",
        "recent_activity", "key_investments",
    ]
    meta_fields = [
        "url_quality", "email_confidence", "email_source",
        "aum_source", "activity_date", "activity_source_url",
    ]
    score = 0
    total_weight = 0
    for f in core_fields:
        total_weight += 3
        if record.get(f) and str(record[f]).lower() not in ("unknown", "not found", "none"):
            score += 3
    for f in secondary_fields:
        total_weight += 2
        if record.get(f) and str(record[f]).lower() not in ("unknown", "not found", "none"):
            score += 2
    for f in meta_fields:
        total_weight += 1
        if record.get(f) and str(record[f]).lower() not in ("unknown", "not found", "none"):
            score += 1
    return round((score / total_weight) * 100, 1) if total_weight > 0 else 0.0


def _compute_confidence(record: Dict, candidate: Dict) -> float:
    """Calculate overall confidence score (0-100)."""
    score = 0.0
    source = candidate.get("source", "")
    if source == "seed_list":
        score += 30
    elif source == "sec_edgar":
        score += 25
    elif source == "propublica":
        score += 20
    else:
        score += 10

    url_quality = record.get("url_quality", "Not Found")
    quality_scores = {"Highest": 25, "Medium": 18, "Medium-Low": 12, "Lower": 6, "Not Found": 0}
    score += quality_scores.get(url_quality, 0)

    key_fields = [
        "description", "investment_thesis", "investing_sectors", "hq_city",
        "hq_country", "contact_name", "contact_title", "entity_type",
        "year_founded", "aum_estimated", "key_investments", "recent_activity",
    ]
    filled = sum(1 for f in key_fields if record.get(f) and str(record[f]).lower() not in ("unknown", "not found"))
    score += min(filled * 2.5, 30)

    if record.get("contact_name") and str(record["contact_name"]).lower() != "unknown":
        score += 5
    if record.get("contact_email"):
        score += 5
    if record.get("contact_title"):
        score += 3
    if record.get("corporate_linkedin_url"):
        score += 2

    return min(round(score, 1), 100.0)


def _search_aum_web(name: str) -> Optional[Dict]:
    """Search web for AUM data from news, Wikipedia, or industry sources."""
    from ..discovery.web_search import _brave_search

    queries = [
        f'"{name}" "assets under management"',
        f'"{name}" AUM billion',
        f'"{name}" manages billion assets',
    ]
    for query in queries:
        try:
            results = _brave_search(query, max_results=5)
            for r in results:
                text = f"{r.get('title', '')} {r.get('text', '')}"
                aum = _extract_aum_from_text(text, name)
                if aum:
                    source_url = r.get("url", "Web search")
                    return {"aum": aum, "source": f"Web search ({source_url[:60]})"}
            time.sleep(0.5)
        except Exception as e:
            logger.debug(f"AUM web search failed for '{name}': {e}")
            continue
    return None


def _extract_aum_from_text(text: str, name: str) -> Optional[str]:
    """Extract AUM figure from search result text."""
    if not text:
        return None
    name_words = [w.lower() for w in name.split() if len(w) > 3]
    text_lower = text.lower()
    if not any(w in text_lower for w in name_words):
        return None

    patterns = [
        r'\$\s*([\d,.]+)\s*(trillion|billion|million)\s*(?:in\s+)?(?:assets?\s+under\s+management|AUM|assets)',
        r'(?:AUM|assets?\s+under\s+management|manages?|managing)\s*(?:of\s+)?(?:approximately\s+)?\$\s*([\d,.]+)\s*(trillion|billion|million)',
        r'\$\s*([\d,.]+)\s*(trillion|billion|million)\s*(?:fund|portfolio|capital)',
        r'(?:oversee|manage|administer)s?\s+(?:approximately\s+)?\$\s*([\d,.]+)\s*(trillion|billion|million)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            amount = groups[0].replace(",", "")
            unit = groups[1].lower() if len(groups) > 1 else ""
            try:
                num = float(amount)
                if unit == "trillion" and num <= 5:
                    return f"${amount} {unit.title()}"
                elif unit == "billion" and 0.1 <= num <= 500:
                    return f"${amount} Billion"
                elif unit == "million" and 10 <= num <= 999:
                    return f"${amount} Million"
            except ValueError:
                continue
    return None


def _search_contact_linkedin(contact_name: str, company_name: str) -> Optional[str]:
    """Search web for a contact's LinkedIn profile URL.

    Uses Brave Search with name+company verification.
    Returns URL ONLY if the result matches both name and company.
    NO fallback — returns None if not found (never generates fake URLs).
    """
    from ..discovery.web_search import _brave_search

    if not contact_name or contact_name.lower() in ("unknown", "n/a"):
        return None

    query = f'"{contact_name}" "{company_name}" site:linkedin.com/in/'
    try:
        results = _brave_search(query, max_results=5)

        for r in results:
            url = r.get("url", "")
            title = r.get("title", "")
            text = r.get("text", "")

            if "linkedin.com/in/" not in url.lower():
                continue

            combined = f"{title} {text}".lower()
            name_parts = contact_name.lower().split()
            last_name = name_parts[-1] if name_parts else ""
            company_words = [w.lower() for w in company_name.split() if len(w) > 3]

            if not (last_name and len(last_name) > 2 and last_name in combined):
                continue

            company_match = any(w in combined for w in company_words) if company_words else True

            if company_match:
                clean_url = url.split("?")[0]
                if not clean_url.endswith("/"):
                    clean_url += "/"
                logger.debug(f"Verified LinkedIn for {contact_name} at {company_name}: {clean_url}")
                return clean_url

    except Exception as e:
        logger.debug(f"Contact LinkedIn search failed for '{contact_name}': {e}")

    logger.debug(f"No verified LinkedIn found for {contact_name} at {company_name}")
    return None


def _parse_team_members_from_content(content: str) -> List[Dict]:
    """Parse team members from scraper output's TEAM_MEMBERS marker.

    The BFS scraper embeds structured data as:
    === TEAM_MEMBERS ===
    Name | Title | email | linkedin_url
    """
    members = []
    if not content or "TEAM_MEMBERS" not in content:
        return members

    try:
        marker = "=== TEAM_MEMBERS ==="
        idx = content.index(marker)
        section = content[idx + len(marker):]

        end_idx = section.find("\n===")
        if end_idx > 0:
            section = section[:end_idx]

        for line in section.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if not parts or not parts[0]:
                continue
            member = {"name": parts[0]}
            if len(parts) > 1 and parts[1]:
                member["title"] = parts[1]
            if len(parts) > 2 and parts[2] and "@" in parts[2]:
                member["email"] = parts[2]
            if len(parts) > 3 and parts[3] and "linkedin.com" in parts[3]:
                member["linkedin"] = parts[3]
            members.append(member)

    except (ValueError, IndexError):
        pass

    return members


def _parse_emails_from_content(content: str) -> List[str]:
    """Parse extracted emails from scraper output's EXTRACTED_EMAILS marker."""
    emails = []
    if not content or "EXTRACTED_EMAILS" not in content:
        return emails

    try:
        marker = "=== EXTRACTED_EMAILS ==="
        idx = content.index(marker)
        section = content[idx + len(marker):]

        end_idx = section.find("\n===")
        if end_idx > 0:
            section = section[:end_idx]

        for line in section.strip().split("\n"):
            email = line.strip()
            if email and "@" in email:
                emails.append(email)

    except (ValueError, IndexError):
        pass

    return emails
