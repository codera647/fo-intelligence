"""
Stage 4: Tavily Search Contact Discovery
==========================================
Three-tier contact enrichment using Tavily Search API:

  Tier 1 — Has team members with partial contacts → fill gaps
  Tier 2 — Has team member names but no contact info → find both
  Tier 3 — No real team members → discover people + find contacts

Priority order per FO:
  1. Free methods first (email pattern inference from existing emails)
  2. Tavily Search API for LinkedIn profiles + email discovery
  3. SMTP verification for email candidates

Input:  02_enriched_family_offices.json (from Stage 2+3)
Output: 03_contacts_enriched.json

Usage:
    from src.enrichment.google_contact_search import enrich_fo_contacts
    enriched = enrich_fo_contacts(fo_record)
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

# ─── Global query counter ─────────────────────────────────────────
_query_count = 0

TAVILY_API_URL = "https://api.tavily.com/search"

# Names that indicate GPT returned a template placeholder, not real data
PLACEHOLDER_NAMES = {
    "full name", "name", "first last", "john doe", "jane doe",
    "their title/role", "team member", "contact person",
}

# Title keywords scored by relevance for family office outreach
TITLE_SCORES = {
    "chief investment officer": 10, "cio": 10,
    "managing director": 9, "managing partner": 9, "managing member": 9,
    "head of investments": 9, "director of investments": 8,
    "general partner": 8, "partner": 8,
    "founder": 8, "co-founder": 8,
    "chief executive": 7, "ceo": 7,
    "president": 7,
    "chief financial": 6, "cfo": 6,
    "chief operating": 6, "coo": 6,
    "principal": 6,
    "investment director": 7,
    "portfolio manager": 5,
    "senior vice president": 5, "svp": 5,
    "vice president": 4, "vp": 4,
    "director": 4,
    "head of": 5,
    "senior advisor": 3, "senior adviser": 3,
    "advisor": 2, "adviser": 2,
    "analyst": 1, "associate": 1,
}


# ═══════════════════════════════════════════════════════════════════
# Tavily Search API
# ═══════════════════════════════════════════════════════════════════

def get_query_count() -> int:
    """Return the total number of Tavily API queries used this session."""
    return _query_count


def _tavily_search(query: str, num: int = 5) -> list[dict]:
    """Execute a Tavily Search query.

    Returns list of result items normalised to {title, link, snippet}
    (same shape the rest of the module expects).
    Increments global query counter.
    """
    global _query_count

    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not configured — skipping search")
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
        raw_results = data.get("results", [])

        # Normalise to Google-style {title, link, snippet} so downstream
        # parsers don't need changing.
        items = []
        for r in raw_results:
            items.append({
                "title": r.get("title", ""),
                "link": r.get("url", ""),
                "snippet": r.get("content", ""),
            })

        logger.debug(
            f"  Tavily [{_query_count}] '{query[:60]}…' → {len(items)} results"
        )
        return items
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("  Tavily rate limit hit — waiting 5s")
            time.sleep(5)
            return []
        logger.warning(f"  Tavily search HTTP error: {e.response.status_code}")
        return []
    except Exception as e:
        logger.warning(f"  Tavily search failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _extract_domain(url: str) -> str:
    """Extract base domain from URL. 'https://www.example.com/p' → 'example.com'"""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = (parsed.netloc or parsed.path).lower()
        domain = domain.replace("www.", "")
        # Remove port if present
        domain = domain.split(":")[0]
        return domain
    except Exception:
        return ""


def _verify_mx(domain: str) -> bool:
    """Check if domain has MX records (can receive email)."""
    if not domain:
        return False
    try:
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False


def _split_name(full_name: str) -> tuple[str, str]:
    """Split full name into (first, last). Returns ('', '') if unparseable."""
    if not full_name:
        return ("", "")
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return (parts[0], parts[-1])
    return (full_name, "")


def _is_placeholder(member: dict) -> bool:
    """Check if a team member entry is a GPT template placeholder."""
    name = (member.get("name") or "").strip().lower()
    title = (member.get("title") or "").strip().lower()
    email = (member.get("email") or "").strip().lower()

    if name in PLACEHOLDER_NAMES:
        return True
    if title in PLACEHOLDER_NAMES or title == "their title/role":
        return True
    if email == "email@domain.com or null":
        return True
    if not name or len(name) < 3:
        return True
    # Single-word names are suspect
    if " " not in name:
        return True
    return False


def _has_real_team(fo: dict) -> bool:
    """Check if FO has at least one non-placeholder team member."""
    members = fo.get("team_members", [])
    return any(not _is_placeholder(m) for m in members)


def _real_members(fo: dict) -> list[dict]:
    """Return only non-placeholder team members."""
    return [m for m in fo.get("team_members", []) if not _is_placeholder(m)]


def _member_has_linkedin(m: dict) -> bool:
    """Check if member has a real LinkedIn URL."""
    url = m.get("linkedin_url") or ""
    return url.startswith("http") and "linkedin.com/in/" in url


def _member_has_email(m: dict) -> bool:
    """Check if member has a real email (not a placeholder)."""
    email = m.get("email") or ""
    return bool(email) and "@" in email and email != "email@domain.com or null"


def _clean_company_name(name: str) -> str:
    """Remove 'Family Office' suffix and clean up for search queries."""
    cleaned = re.sub(r"\s*Family\s*Office\s*$", "", name, flags=re.IGNORECASE).strip()
    # Also remove doubled names like "Mars Family Office Family Office"
    cleaned = re.sub(r"\s*Family\s*Office\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or name


def _title_score(title: str) -> int:
    """Score a title by relevance for FO outreach."""
    if not title:
        return 0
    title_lower = title.lower()
    best = 0
    for keyword, score in TITLE_SCORES.items():
        if keyword in title_lower:
            best = max(best, score)
    return best


# ═══════════════════════════════════════════════════════════════════
# LinkedIn Search
# ═══════════════════════════════════════════════════════════════════

def _parse_linkedin_person(item: dict) -> Optional[dict]:
    """Parse a Google result for a LinkedIn /in/ profile.

    Returns dict with name, title, linkedin_url or None.
    """
    link = item.get("link", "")
    title = item.get("title", "")

    # Must be a personal profile
    if "/in/" not in link:
        return None

    # Clean URL (strip query params, trailing slash)
    url = link.split("?")[0].rstrip("/")

    # Parse title: "Name - Title - Company | LinkedIn" or variants
    clean = title.replace(" | LinkedIn", "").replace(" - LinkedIn", "")
    parts = [p.strip() for p in clean.split(" - ")]

    name = parts[0] if parts else ""
    role = parts[1] if len(parts) > 1 else ""

    # Basic validation
    if not name or len(name) < 3 or name.lower() in PLACEHOLDER_NAMES:
        return None
    if " " not in name:
        return None  # Need first + last name

    return {
        "name": name,
        "title": role,
        "linkedin_url": url,
        "email": None,
        "is_key_contact": False,
    }


def _is_relevant_result(item: dict, company: str) -> bool:
    """Check if a LinkedIn search result is actually related to this company."""
    text = (item.get("title", "") + " " + item.get("snippet", "")).lower()
    company_lower = company.lower()

    # Check full company name
    if company_lower in text:
        return True

    # Check the main distinctive word (first word, or longest word)
    words = _clean_company_name(company).lower().split()
    # Filter out common words
    distinctive = [w for w in words if len(w) > 3 and w not in {
        "the", "group", "capital", "management", "investments", "partners",
        "family", "office", "trust", "fund", "financial", "services",
        "holdings", "enterprises", "international", "global", "advisors",
    }]

    if distinctive:
        return any(w in text for w in distinctive)

    # Fall back to first significant word
    if words:
        return words[0] in text

    return False


def search_person_linkedin(name: str, company: str) -> Optional[str]:
    """Search for a person's LinkedIn profile URL via Tavily.

    Returns LinkedIn URL string or None.
    """
    clean_co = _clean_company_name(company)
    query = f'site:linkedin.com/in "{name}" "{clean_co}"'

    items = _tavily_search(query, num=3)

    for item in items:
        if "/in/" in item.get("link", ""):
            url = item["link"].split("?")[0].rstrip("/")
            # Verify relevance
            if _is_relevant_result(item, company):
                return url

    # Broader search without company constraint
    if not items:
        query2 = f'site:linkedin.com/in "{name}" {clean_co}'
        items2 = _tavily_search(query2, num=3)
        for item in items2:
            if "/in/" in item.get("link", ""):
                if _is_relevant_result(item, company):
                    return item["link"].split("?")[0].rstrip("/")

    return None


def search_company_linkedin(company: str) -> Optional[str]:
    """Search for company's LinkedIn page via Tavily.

    Returns LinkedIn company URL or None.
    """
    clean_co = _clean_company_name(company)
    query = f'site:linkedin.com/company "{clean_co}"'

    items = _tavily_search(query, num=3)

    for item in items:
        link = item.get("link", "")
        if "/company/" in link:
            return link.split("?")[0].rstrip("/")

    return None


def search_team_at_company(company: str) -> list[dict]:
    """Search for LinkedIn profiles of people at this company via Tavily.

    Searches for profiles with relevant FO titles.
    Returns list of {name, title, linkedin_url}.
    """
    clean_co = _clean_company_name(company)
    title_terms = (
        'CIO OR "Managing Director" OR Partner OR CEO OR '
        '"Head of Investments" OR Principal OR "Chief Investment"'
    )
    query = f'site:linkedin.com/in "{clean_co}" ({title_terms})'

    items = _tavily_search(query, num=10)

    results = []
    seen_urls = set()

    for item in items:
        parsed = _parse_linkedin_person(item)
        if not parsed:
            continue
        if parsed["linkedin_url"] in seen_urls:
            continue
        if not _is_relevant_result(item, company):
            continue
        seen_urls.add(parsed["linkedin_url"])
        results.append(parsed)

    # If first search gave nothing, try broader query
    if not results:
        query2 = f'site:linkedin.com/in "{clean_co}" family office'
        items2 = _tavily_search(query2, num=10)

        for item in items2:
            parsed = _parse_linkedin_person(item)
            if not parsed:
                continue
            if parsed["linkedin_url"] in seen_urls:
                continue
            if _is_relevant_result(item, company):
                seen_urls.add(parsed["linkedin_url"])
                results.append(parsed)

    # Sort by title relevance
    results.sort(key=lambda p: _title_score(p.get("title", "")), reverse=True)

    return results


# ═══════════════════════════════════════════════════════════════════
# Email Discovery
# ═══════════════════════════════════════════════════════════════════

def _generate_email_patterns(first: str, last: str, domain: str) -> list[str]:
    """Generate common corporate email patterns."""
    f = first.lower().strip()
    la = last.lower().strip()
    if not f or not la or not domain:
        return []
    fi = f[0]
    return [
        f"{f}.{la}@{domain}",
        f"{fi}{la}@{domain}",
        f"{f}@{domain}",
        f"{f}{la}@{domain}",
        f"{fi}.{la}@{domain}",
        f"{la}.{f}@{domain}",
        f"{la}{fi}@{domain}",
    ]


def _detect_email_pattern(emails: list[str], domain: str) -> Optional[str]:
    """Detect the email pattern used at a domain from known emails.

    Returns pattern string like 'first.last', 'flast', etc.
    """
    if not emails:
        return None

    patterns_found: dict[str, int] = {}

    for email in emails:
        if "@" not in email:
            continue
        local, email_domain = email.split("@", 1)
        if email_domain.lower() != domain.lower():
            continue

        local = local.lower()
        if "." in local:
            parts = local.split(".")
            if len(parts) == 2 and parts[0].isalpha() and parts[1].isalpha():
                if len(parts[0]) > 1 and len(parts[1]) > 1:
                    patterns_found["first.last"] = patterns_found.get("first.last", 0) + 1
                elif len(parts[0]) == 1:
                    patterns_found["f.last"] = patterns_found.get("f.last", 0) + 1
        elif local.isalpha():
            if len(local) > 5:
                patterns_found["firstlast"] = patterns_found.get("firstlast", 0) + 1

    if patterns_found:
        return max(patterns_found, key=patterns_found.get)
    return None


def _apply_pattern(pattern: str, first: str, last: str, domain: str) -> Optional[str]:
    """Apply a detected email pattern to a name."""
    f = first.lower()
    la = last.lower()
    mapping = {
        "first.last": f"{f}.{la}@{domain}",
        "f.last": f"{f[0]}.{la}@{domain}",
        "firstlast": f"{f}{la}@{domain}",
        "flast": f"{f[0]}{la}@{domain}",
    }
    return mapping.get(pattern)


def find_email(
    name: str,
    company: str,
    domain: str,
    has_mx: bool,
    existing_emails: list[str] = None,
) -> Optional[dict]:
    """Find an email address for a person at a company.

    Strategy:
      1. Check if any existing extracted emails match this person
      2. Detect email pattern from existing emails → apply to this person
      3. Google search for email
      4. If domain has MX + known pattern, infer email

    Returns dict with 'email', 'confidence', 'source' or None.
    """
    first, last = _split_name(name)
    if not first or not last or not domain:
        return None

    # ── 1. Direct match in existing extracted emails ──
    if existing_emails:
        f_lower = first.lower()
        l_lower = last.lower()
        for email in existing_emails:
            local = email.split("@")[0].lower()
            if any([
                local == f"{f_lower}.{l_lower}",
                local == f"{f_lower}{l_lower}",
                local == f"{f_lower[0]}{l_lower}",
                local == f"{f_lower}",
            ]):
                return {"email": email, "confidence": "High", "source": "Website match"}

    # ── 2. Pattern inference from existing emails ──
    detected_pattern = None
    if existing_emails:
        detected_pattern = _detect_email_pattern(existing_emails, domain)

    if detected_pattern:
        inferred = _apply_pattern(detected_pattern, first, last, domain)
        if inferred:
            return {"email": inferred, "confidence": "Medium", "source": f"Pattern inference ({detected_pattern})"}

    # ── 3. Google search for email ──
    query = f'"{first} {last}" "@{domain}"'
    items = _tavily_search(query, num=3)

    patterns = _generate_email_patterns(first, last, domain)

    for item in items:
        text = (item.get("snippet", "") + " " + item.get("title", "")).lower()
        for p in patterns:
            if p.lower() in text:
                return {"email": p, "confidence": "High", "source": "Google search"}

    # ── 4. If MX exists + we've seen other emails at this domain, infer ──
    if has_mx and existing_emails:
        best = f"{first.lower()}.{last.lower()}@{domain}"
        return {"email": best, "confidence": "Low", "source": "Domain pattern (unverified)"}

    return None


# ═══════════════════════════════════════════════════════════════════
# Tier Classification
# ═══════════════════════════════════════════════════════════════════

def classify_tier(fo: dict) -> tuple[int, str]:
    """Classify FO into enrichment tier.

    Returns (tier_number, reason_string).
      Tier 1: Has real team members with at least some contacts
      Tier 2: Has real team member names but no contact info
      Tier 3: No real team members at all
    """
    members = _real_members(fo)

    if not members:
        return (3, "No real team members — full discovery needed")

    has_any_contact = any(
        _member_has_linkedin(m) or _member_has_email(m)
        for m in members
    )

    if has_any_contact:
        return (1, f"{len(members)} members, some contacts — fill gaps")
    else:
        return (2, f"{len(members)} members, no contacts — find both")


# ═══════════════════════════════════════════════════════════════════
# Per-Tier Enrichment Logic
# ═══════════════════════════════════════════════════════════════════

def _fill_contact_gaps(fo: dict, domain: str, has_mx: bool):
    """Tier 1: Fill missing LinkedIn/email for team members with partial contacts."""
    company = fo.get("name", "")
    existing_emails = fo.get("extracted_emails", [])

    for member in fo.get("team_members", []):
        if _is_placeholder(member):
            continue

        name = member.get("name", "")
        if not name:
            continue

        # Fill LinkedIn if missing
        if not _member_has_linkedin(member):
            url = search_person_linkedin(name, company)
            if url:
                member["linkedin_url"] = url
                logger.info(f"    ✓ LinkedIn found: {name} → {url}")
            time.sleep(0.3)

        # Fill email if missing
        if not _member_has_email(member) and domain:
            result = find_email(name, company, domain, has_mx, existing_emails)
            if result:
                member["email"] = result["email"]
                logger.info(f"    ✓ Email ({result['confidence']}): {name} → {result['email']}")
            time.sleep(0.3)


def _find_team_contacts(fo: dict, domain: str, has_mx: bool):
    """Tier 2: Find LinkedIn and email for named team members (no existing contacts)."""
    company = fo.get("name", "")
    existing_emails = fo.get("extracted_emails", [])

    for member in fo.get("team_members", []):
        if _is_placeholder(member):
            continue

        name = member.get("name", "")
        if not name:
            continue

        # Search LinkedIn
        url = search_person_linkedin(name, company)
        if url:
            member["linkedin_url"] = url
            logger.info(f"    ✓ LinkedIn: {name} → {url}")
        time.sleep(0.3)

        # Search email
        if domain:
            result = find_email(name, company, domain, has_mx, existing_emails)
            if result:
                member["email"] = result["email"]
                logger.info(f"    ✓ Email ({result['confidence']}): {name} → {result['email']}")
            time.sleep(0.3)


def _discover_team(fo: dict, domain: str, has_mx: bool):
    """Tier 3: Discover team members from scratch via Google LinkedIn search."""
    company = fo.get("name", "")
    existing_emails = fo.get("extracted_emails", [])

    # Search for people at this company on LinkedIn
    results = search_team_at_company(company)
    time.sleep(0.5)

    if not results:
        logger.info(f"    ✗ No team members found via Tavily")
        return

    # Take top 3 most relevant people
    top = results[:3]
    logger.info(f"    Found {len(results)} profiles, keeping top {len(top)}")

    # Build team_members list
    team = []
    for person in top:
        member = {
            "name": person["name"],
            "title": person.get("title", ""),
            "linkedin_url": person["linkedin_url"],
            "email": None,
            "is_key_contact": True,
        }

        # Try to find email
        if domain:
            result = find_email(person["name"], company, domain, has_mx, existing_emails)
            if result:
                member["email"] = result["email"]
                logger.info(f"    ✓ Email ({result['confidence']}): {person['name']} → {result['email']}")
            time.sleep(0.3)

        team.append(member)

    # Merge discovered team with any existing (non-placeholder) members
    existing_real = _real_members(fo)
    existing_names = {m.get("name", "").lower() for m in existing_real}

    for person in team:
        if person["name"].lower() not in existing_names:
            existing_real.append(person)

    fo["team_members"] = existing_real
    fo["team_size"] = len(existing_real)

    # Update best_contacts
    fo["best_contacts"] = [
        {
            "name": m["name"],
            "title": m.get("title", ""),
            "reason": "Discovered via Tavily Search — key decision maker",
        }
        for m in sorted(existing_real,
                        key=lambda x: _title_score(x.get("title", "")),
                        reverse=True)[:3]
    ]

    fo["contact_source"] = "TavilySearch"


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

def enrich_fo_contacts(fo: dict) -> dict:
    """Enrich a single FO record with contact information.

    Classifies into tier, runs appropriate search strategy,
    and returns the enriched record.
    """
    enriched = dict(fo)  # shallow copy
    name = enriched.get("name", "Unknown")
    website = enriched.get("website", "")
    domain = _extract_domain(website)

    tier, reason = classify_tier(enriched)
    enriched["contact_enrichment_tier"] = tier

    logger.info(f"  Tier {tier}: {reason}")

    # Check MX once per domain (free, no API cost)
    has_mx = _verify_mx(domain) if domain else False
    if domain:
        logger.debug(f"  Domain: {domain}, MX: {'✓' if has_mx else '✗'}")

    queries_before = _query_count

    # ── Run tier-specific enrichment ──
    if tier == 1:
        _fill_contact_gaps(enriched, domain, has_mx)
    elif tier == 2:
        _find_team_contacts(enriched, domain, has_mx)
    elif tier == 3:
        _discover_team(enriched, domain, has_mx)

    # ── Always try corporate LinkedIn if missing ──
    if not enriched.get("corporate_linkedin"):
        corp_url = search_company_linkedin(name)
        if corp_url:
            enriched["corporate_linkedin"] = corp_url
            logger.info(f"    ✓ Corporate LinkedIn: {corp_url}")
        time.sleep(0.3)

    queries_used = _query_count - queries_before
    enriched["tavily_queries_used"] = queries_used

    return enriched
