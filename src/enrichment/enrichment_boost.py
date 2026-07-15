"""
Stage 4.5: Enrichment Boost
============================
Post-scoring quality improvements applied to 03_contacts_enriched.json:

  1. MX Email Verification   — domains with valid MX → "Medium" bumped to "High"
  2. Recent Activity Search  — Tavily queries for FOs missing recent_activity
  3. Email Discovery         — Tavily queries for FOs missing contact emails
  4. Deduplication           — merge known-duplicate FO entries
  5. Placeholder Filtering   — remove fake contacts ("John Doe") + malformed emails
  6. Country Mapping Fix     — non-US FOs no longer default to "United States"

Input:  data/pipeline/03_contacts_enriched.json
Output: data/pipeline/03_contacts_enriched.json  (overwritten, backup saved)

Usage:
    from src.enrichment.enrichment_boost import boost_all
    boosted = boost_all(records)
"""

import re
import time
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
import dns.resolver

from config.settings import TAVILY_API_KEY

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"

_query_count = 0

# ═══════════════════════════════════════════════════════════════════
# Known duplicates — map secondary names → primary (keep primary)
# ═══════════════════════════════════════════════════════════════════

KNOWN_DUPLICATES = {
    # slug or name (lowered) of the DUPLICATE → slug/name of the one to KEEP
    "ken griffin family office": "citadel llc",
    "ken griffin": "citadel llc",
    "cofra holding / brenninkmeijer family": "cofra holding",
    "cofra holding / brenninkmeijer": "cofra holding",
    "brenninkmeijer family office": "cofra holding",
}

# ═══════════════════════════════════════════════════════════════════
# Placeholder / bad-data filters
# ═══════════════════════════════════════════════════════════════════

PLACEHOLDER_NAMES = {
    "john doe", "jane doe", "full name", "name", "first last",
    "team member", "contact person", "unknown", "n/a",
    "leadership team", "management team", "executive team",
}

# Non-US locations → correct country mapping
# city keywords that hint the FO is outside the US
NON_US_CITY_MARKERS = {
    "london": "United Kingdom",
    "zurich": "Switzerland",
    "zürich": "Switzerland",
    "geneva": "Switzerland",
    "geneve": "Switzerland",
    "munich": "Germany",
    "frankfurt": "Germany",
    "paris": "France",
    "hong kong": "Hong Kong",
    "singapore": "Singapore",
    "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates",
    "riyadh": "Saudi Arabia",
    "mumbai": "India",
    "new delhi": "India",
    "tokyo": "Japan",
    "sydney": "Australia",
    "melbourne": "Australia",
    "toronto": "Canada",
    "vancouver": "Canada",
    "montreal": "Canada",
    "amsterdam": "Netherlands",
    "stockholm": "Sweden",
    "oslo": "Norway",
    "copenhagen": "Denmark",
    "luxembourg": "Luxembourg",
    "brussels": "Belgium",
    "milan": "Italy",
    "rome": "Italy",
    "madrid": "Spain",
    "barcelona": "Spain",
    "lisbon": "Portugal",
    "dublin": "Ireland",
    "edinburgh": "United Kingdom",
    "tel aviv": "Israel",
    "beijing": "China",
    "shanghai": "China",
    "kuala lumpur": "Malaysia",
    "jakarta": "Indonesia",
    "bangkok": "Thailand",
    "seoul": "South Korea",
    "taipei": "Taiwan",
    "manila": "Philippines",
    "lagos": "Nigeria",
    "nairobi": "Kenya",
    "johannesburg": "South Africa",
    "cape town": "South Africa",
    "sao paulo": "Brazil",
    "mexico city": "Mexico",
    "buenos aires": "Argentina",
    "bogota": "Colombia",
    "lima": "Peru",
}

# Country-name indicators in the HQ string itself
COUNTRY_KEYWORDS = {
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "united kingdom": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "switzerland": "Switzerland",
    "germany": "Germany",
    "france": "France",
    "canada": "Canada",
    "australia": "Australia",
    "india": "India",
    "japan": "Japan",
    "china": "China",
    "brazil": "Brazil",
    "mexico": "Mexico",
    "singapore": "Singapore",
    "hong kong": "Hong Kong",
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "saudi arabia": "Saudi Arabia",
    "israel": "Israel",
    "netherlands": "Netherlands",
    "sweden": "Sweden",
    "norway": "Norway",
    "denmark": "Denmark",
    "ireland": "Ireland",
    "italy": "Italy",
    "spain": "Spain",
}


# ═══════════════════════════════════════════════════════════════════
# Tavily wrapper (local to this module)
# ═══════════════════════════════════════════════════════════════════

def _tavily_search(query: str, num: int = 5) -> list[dict]:
    """Execute a Tavily Search query. Returns [{title, link, snippet}]."""
    global _query_count

    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not set — skipping search")
        return []

    _query_count += 1

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": min(num, 10),
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        resp = httpx.post(TAVILY_API_URL, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = []
        for r in data.get("results", []):
            items.append({
                "title": r.get("title", ""),
                "link": r.get("url", ""),
                "snippet": r.get("content", ""),
            })
        logger.debug(f"  Tavily [{_query_count}] '{query[:60]}…' → {len(items)} results")
        return items
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("  Tavily rate limit — waiting 5s")
            time.sleep(5)
            return []
        logger.warning(f"  Tavily HTTP error: {e.response.status_code}")
        return []
    except Exception as e:
        logger.warning(f"  Tavily search failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# 1. MX Email Verification
# ═══════════════════════════════════════════════════════════════════

def _extract_domain(email: str) -> str:
    """Get domain part from email address."""
    if not email or "@" not in email:
        return ""
    return email.strip().split("@")[-1].lower()


def _verify_mx(domain: str) -> bool:
    """Check if domain has valid MX records."""
    if not domain:
        return False
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(answers) > 0
    except Exception:
        return False


def verify_emails_mx(records: list[dict]) -> int:
    """Verify MX records for all team member emails.

    Updates email_confidence: "Medium" → "High" if MX valid.
    Returns count of upgrades.
    """
    upgraded = 0
    domains_cache: dict[str, bool] = {}

    for rec in records:
        team = rec.get("team_members") or []
        for member in team:
            email = member.get("email", "")
            if not email or "@" not in email:
                continue

            domain = _extract_domain(email)
            if not domain:
                continue

            # Cache domain lookups
            if domain not in domains_cache:
                domains_cache[domain] = _verify_mx(domain)

            if domains_cache[domain]:
                old_conf = member.get("email_confidence", "")
                if old_conf in ("Medium", ""):
                    member["email_confidence"] = "High"
                    member["email_source"] = (
                        member.get("email_source", "Pattern-inferred")
                        + " + MX verified"
                    )
                    upgraded += 1
            else:
                # MX failed — downgrade if currently Medium
                old_conf = member.get("email_confidence", "")
                if old_conf == "Medium":
                    member["email_confidence"] = "Low"
                    member["email_source"] = (
                        member.get("email_source", "Pattern-inferred")
                        + " (MX failed)"
                    )

        # Also check extracted_emails (corporate)
        extracted = rec.get("extracted_emails") or []
        verified_extracted = []
        for em in extracted:
            d = _extract_domain(em)
            if d and d not in domains_cache:
                domains_cache[d] = _verify_mx(d)
            if d and domains_cache.get(d, False):
                verified_extracted.append(em)
        if verified_extracted:
            rec["extracted_emails"] = verified_extracted

    logger.info(f"  MX verification: {upgraded} emails upgraded, {len(domains_cache)} domains checked")
    return upgraded


# ═══════════════════════════════════════════════════════════════════
# 2. Recent Activity Search via Tavily
# ═══════════════════════════════════════════════════════════════════

def _extract_date_from_snippet(snippet: str) -> Optional[str]:
    """Try to extract a date (YYYY-MM-DD or similar) from snippet text."""
    # Match patterns like "Jan 15, 2025", "2024-12-01", "December 2024"
    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})",
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, snippet, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def search_recent_activity(records: list[dict], max_queries: int = 60) -> int:
    """Search for recent news/activity for FOs missing it.

    Updates rec["recent_activity"] dict with {title, date, url}.
    Returns count of FOs enriched.
    """
    enriched = 0
    queries_used = 0

    for rec in records:
        if queries_used >= max_queries:
            logger.info(f"  Activity search: hit query limit ({max_queries})")
            break

        # Skip if already has activity
        existing = rec.get("recent_activity")
        if isinstance(existing, dict) and existing.get("title"):
            continue

        fo_name = rec.get("name", "")
        if not fo_name:
            continue

        # Search for recent news
        query = f'"{fo_name}" family office investment news 2024 2025'
        results = _tavily_search(query, num=5)
        queries_used += 1
        time.sleep(0.5)  # Rate limiting

        if not results:
            continue

        # Pick best result — prefer ones mentioning the FO name
        best = None
        for r in results:
            combined = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            # Must mention the FO name (or a key word from it)
            name_words = [w.lower() for w in fo_name.split() if len(w) > 3]
            if any(w in combined for w in name_words):
                best = r
                break

        if not best:
            # Fallback: just use first result if it looks relevant
            first = results[0]
            snippet = first.get("snippet", "").lower()
            if "family office" in snippet or "investment" in snippet:
                best = first

        if best:
            date_str = _extract_date_from_snippet(best.get("snippet", ""))
            rec["recent_activity"] = {
                "title": best["title"][:200],
                "date": date_str,
                "url": best["link"],
                "summary": best.get("snippet", "")[:300],
            }
            enriched += 1
            logger.debug(f"  Activity found for {fo_name}: {best['title'][:60]}")

    logger.info(f"  Activity search: {enriched} FOs enriched, {queries_used} queries used")
    return enriched


# ═══════════════════════════════════════════════════════════════════
# 3. Email Discovery for FOs missing contact emails
# ═══════════════════════════════════════════════════════════════════

def _extract_emails_from_text(text: str) -> list[str]:
    """Extract email addresses from text snippet."""
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    found = re.findall(pattern, text)
    # Filter out obvious junk
    filtered = []
    for em in found:
        em_lower = em.lower()
        if any(x in em_lower for x in ["example.com", "test.com", "email.com", "sentry.io"]):
            continue
        filtered.append(em)
    return filtered


def _infer_email_pattern(fo_name: str, domain: str, contact_name: str) -> Optional[str]:
    """Infer email from name + domain using common patterns."""
    if not domain or not contact_name:
        return None

    parts = contact_name.strip().split()
    if len(parts) < 2:
        return None

    first = parts[0].lower()
    last = parts[-1].lower()

    # Most common corporate pattern
    return f"{first}.{last}@{domain}"


def search_missing_emails(records: list[dict], max_queries: int = 40) -> int:
    """Search for emails of FOs that have LinkedIn contacts but no email.

    Returns count of emails found.
    """
    found = 0
    queries_used = 0

    for rec in records:
        if queries_used >= max_queries:
            logger.info(f"  Email search: hit query limit ({max_queries})")
            break

        team = rec.get("team_members") or []
        fo_name = rec.get("name", "")
        website = rec.get("website") or ""
        domain = ""
        if website:
            try:
                parsed = urlparse(website if "://" in website else f"https://{website}")
                domain = (parsed.netloc or "").replace("www.", "").split(":")[0]
            except Exception:
                pass

        # Find team members with LinkedIn but no email
        for member in team:
            if queries_used >= max_queries:
                break

            has_linkedin = member.get("linkedin_url") and "linkedin.com/in/" in (member.get("linkedin_url") or "")
            has_email = member.get("email") and "@" in str(member.get("email", ""))

            if has_linkedin and not has_email:
                name = member.get("name", "")
                if not name or name.lower() in PLACEHOLDER_NAMES:
                    continue

                # Strategy 1: Infer from domain if we have a website
                if domain:
                    inferred = _infer_email_pattern(fo_name, domain, name)
                    if inferred:
                        member["email"] = inferred
                        member["email_confidence"] = "Medium"
                        member["email_source"] = "Pattern-inferred from website domain"
                        found += 1
                        continue

                # Strategy 2: Tavily search for email
                query = f'"{name}" "{fo_name}" email contact'
                results = _tavily_search(query, num=3)
                queries_used += 1
                time.sleep(0.5)

                for r in results:
                    text = r.get("snippet", "") + " " + r.get("title", "")
                    emails = _extract_emails_from_text(text)
                    if emails:
                        member["email"] = emails[0]
                        member["email_confidence"] = "Medium"
                        member["email_source"] = "Tavily search discovery"
                        found += 1
                        break

    logger.info(f"  Email search: {found} emails found, {queries_used} queries used")
    return found


# ═══════════════════════════════════════════════════════════════════
# 4. Deduplication
# ═══════════════════════════════════════════════════════════════════

def deduplicate_records(records: list[dict]) -> list[dict]:
    """Remove known duplicate FOs, keeping the richer record.

    Also catches exact-name duplicates (case-insensitive).
    """
    removed = 0

    # Build lookup of known duplicate names
    dup_names = set()
    for dup_name in KNOWN_DUPLICATES:
        dup_names.add(dup_name.lower())

    deduped = []
    seen_names = set()

    for rec in records:
        name = (rec.get("name") or "").strip()
        name_lower = name.lower()
        slug = (rec.get("slug") or "").lower()

        # Check known duplicates
        if name_lower in dup_names or slug in dup_names:
            removed += 1
            logger.debug(f"  Removed known duplicate: {name}")
            continue

        # Check case-insensitive exact dupes
        # Normalize: strip trailing "Family Office" for comparison
        compare_name = name_lower
        if compare_name.endswith(" family office"):
            compare_name = compare_name[:-len(" family office")].strip()

        if compare_name in seen_names:
            removed += 1
            logger.debug(f"  Removed exact duplicate: {name}")
            continue

        seen_names.add(compare_name)
        deduped.append(rec)

    logger.info(f"  Deduplication: removed {removed} duplicates, {len(deduped)} remain")
    return deduped


# ═══════════════════════════════════════════════════════════════════
# 5. Placeholder + Bad Data Filtering
# ═══════════════════════════════════════════════════════════════════

def _is_placeholder_name(name: str) -> bool:
    """Check if a contact name is a placeholder or company-as-person."""
    if not name:
        return True
    name_lower = name.strip().lower()

    # Direct placeholder match
    if name_lower in PLACEHOLDER_NAMES:
        return True

    # Company-name-as-person: contains words like "Team", "Group", "LLC", "Inc"
    company_indicators = [
        "leadership team", "management team", "executive team",
        "family office", "holdings", " llc", " inc", " ltd",
        " group", " capital", " partners", " management",
        " trust company", " advisors",
    ]
    if any(ind in name_lower for ind in company_indicators):
        return True

    # Single word is suspicious (but allow common single names)
    if len(name.strip().split()) < 2:
        return True

    return False


def _is_malformed_email(email: str) -> bool:
    """Check for structural email issues like misplaced characters."""
    if not email:
        return False
    # Check for stray parentheses, brackets, spaces
    if re.search(r'[)(}\]{\[\s]', email.split("@")[0]):
        return True
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email.strip()):
        return True
    return False


def clean_placeholder_contacts(records: list[dict]) -> int:
    """Remove placeholder contacts and malformed emails from team members.

    Returns count of cleaned entries.
    """
    cleaned = 0

    for rec in records:
        team = rec.get("team_members") or []
        cleaned_team = []

        for member in team:
            name = member.get("name", "")

            # Skip placeholder names
            if _is_placeholder_name(name):
                cleaned += 1
                logger.debug(f"  Removed placeholder contact: {name}")
                continue

            # Fix malformed emails
            email = member.get("email", "")
            if email and _is_malformed_email(email):
                logger.debug(f"  Removed malformed email: {email}")
                member["email"] = None
                member["email_confidence"] = "Not Found"
                member["email_source"] = None
                cleaned += 1

            cleaned_team.append(member)

        rec["team_members"] = cleaned_team

    logger.info(f"  Placeholder cleanup: {cleaned} entries cleaned")
    return cleaned


# ═══════════════════════════════════════════════════════════════════
# 6. Country Mapping Fix
# ═══════════════════════════════════════════════════════════════════

def fix_country_mapping(records: list[dict]) -> int:
    """Fix headquarters country for non-US FOs.

    Checks city names and existing location strings against known
    non-US indicators. Returns count of fixes.
    """
    fixed = 0

    for rec in records:
        hq = rec.get("headquarters") or rec.get("location") or ""
        if not hq:
            continue

        hq_lower = hq.lower().strip()
        hq_parts = [p.strip() for p in hq.split(",")]

        # Already has 3+ parts with explicit country — check if country matches
        if len(hq_parts) >= 3:
            country_part = hq_parts[-1].strip().lower()
            if country_part in COUNTRY_KEYWORDS:
                # Has explicit country — tag it for scorer
                rec["_resolved_country"] = COUNTRY_KEYWORDS[country_part]
                continue

        # Check city name against non-US markers
        city = hq_parts[0].strip().lower() if hq_parts else ""
        if city in NON_US_CITY_MARKERS:
            rec["_resolved_country"] = NON_US_CITY_MARKERS[city]
            fixed += 1
            continue

        # Check if any part of HQ string contains country keywords
        for keyword, country in COUNTRY_KEYWORDS.items():
            if keyword in hq_lower:
                rec["_resolved_country"] = country
                fixed += 1
                break

    logger.info(f"  Country mapping: {fixed} non-US FOs fixed")
    return fixed


# ═══════════════════════════════════════════════════════════════════
# Master orchestrator
# ═══════════════════════════════════════════════════════════════════

def boost_all(
    records: list[dict],
    skip_tavily: bool = False,
    max_activity_queries: int = 60,
    max_email_queries: int = 40,
) -> list[dict]:
    """Run all enrichment boosts on the records list (in-place).

    Args:
        records: List of FO records from 03_contacts_enriched.json
        skip_tavily: If True, skip Tavily searches (MX + cleanup only)
        max_activity_queries: Max Tavily queries for recent activity
        max_email_queries: Max Tavily queries for email discovery

    Returns:
        Boosted records list (same objects, modified in-place)
    """
    logger.info("=" * 60)
    logger.info("STAGE 4.5: Enrichment Boost")
    logger.info("=" * 60)
    logger.info(f"  Input: {len(records)} FOs")

    # 1. Deduplication first (reduces work for subsequent steps)
    records = deduplicate_records(records)

    # 2. Placeholder + bad data cleanup
    clean_placeholder_contacts(records)

    # 3. Country mapping fix
    fix_country_mapping(records)

    # 4. MX email verification (no API cost)
    verify_emails_mx(records)

    # 5-6. Tavily searches (costs API queries)
    if not skip_tavily:
        search_recent_activity(records, max_queries=max_activity_queries)
        search_missing_emails(records, max_queries=max_email_queries)
    else:
        logger.info("  Skipping Tavily searches (skip_tavily=True)")

    logger.info(f"  Tavily queries used this session: {_query_count}")
    logger.info("=" * 60)

    return records
