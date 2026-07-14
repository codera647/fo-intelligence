"""ProPublica Nonprofit Explorer enrichment — pulls Form 990 data for associated foundations.

Many family offices have an associated charitable foundation that files IRS Form 990.
These filings contain:
  - Total assets and revenue
  - Officer/trustee names and titles
  - Principal address
  - Mission/activity description

ProPublica API is free, no key needed, rate limit ~3 req/sec.
"""

import re
import time
import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "FO-Intelligence/1.0 (research@fo-intelligence.com)",
    "Accept": "application/json",
}

# Cache lookups
_search_cache: Dict[str, Optional[Dict]] = {}

# Common family-to-foundation name mappings
FAMILY_FOUNDATION_PATTERNS = [
    "{name} Foundation",
    "{name} Family Foundation",
    "{family} Foundation",
    "{family} Family Foundation",
    "{family} Charitable Foundation",
    "{family} Charitable Trust",
]


def enrich_from_propublica(name: str, existing_data: Dict) -> Dict:
    """Enrich a family office record using ProPublica Nonprofit Explorer.

    Searches for associated charitable foundations, extracts officer data,
    assets, and address info from their latest Form 990.

    Returns dict of fields to merge (only non-empty values).
    """
    result = {}

    try:
        # Extract family name from entity name
        family_name = _extract_family_name(name)

        # Try various foundation name patterns
        search_terms = _generate_search_terms(name, family_name)

        foundation_data = None
        for term in search_terms:
            foundation_data = _search_foundation(term)
            if foundation_data:
                break
            time.sleep(0.3)

        if not foundation_data:
            return {}

        # Get full 990 filing details
        ein = foundation_data.get("ein")
        if not ein:
            return {}

        time.sleep(0.3)
        filing_data = _get_latest_filing(ein)

        # Extract address
        if not existing_data.get("hq_city"):
            city = foundation_data.get("city")
            if city:
                result["hq_city"] = city.title()

        if not existing_data.get("hq_state"):
            state = foundation_data.get("state")
            if state:
                result["hq_state"] = _state_code_to_name(state)

        if not existing_data.get("hq_country"):
            state = foundation_data.get("state")
            if state and len(state) == 2:
                result["hq_country"] = "United States of America"

        if not existing_data.get("hq_street_address"):
            street = foundation_data.get("address")
            if street:
                result["hq_street_address"] = street.title()

        # Extract AUM from total assets
        if not existing_data.get("aum_estimated"):
            total_assets = foundation_data.get("total_assets")
            if total_assets and total_assets > 0:
                result["aum_estimated"] = _format_assets(total_assets)
                result["aum_source"] = "ProPublica Nonprofit Explorer (Form 990)"

        # Extract officers from filing
        if filing_data and not existing_data.get("contact_name"):
            officers = filing_data.get("officers", [])
            if officers:
                # Get the top officer (usually president/chair)
                top_officer = _get_top_officer(officers)
                if top_officer:
                    if not existing_data.get("contact_name"):
                        result["contact_name"] = top_officer.get("name", "").title()
                    if not existing_data.get("contact_title"):
                        result["contact_title"] = top_officer.get("title", "").title()

        # Activity from filing
        if filing_data and not existing_data.get("recent_activity"):
            tax_period = filing_data.get("tax_prd_yr")
            if tax_period:
                foundation_name = foundation_data.get("name", "foundation")
                result["recent_activity"] = f"Form 990 filed for tax year {tax_period} ({foundation_name})"
                result["activity_date"] = str(tax_period)
                result["activity_source_url"] = (
                    f"https://projects.propublica.org/nonprofits/organizations/{ein}"
                )

        if result:
            logger.info(f"ProPublica enriched {len(result)} fields for {name} (EIN: {ein})")

        return result

    except Exception as e:
        logger.warning(f"ProPublica enrichment failed for {name}: {e}")
        return {}


def _extract_family_name(entity_name: str) -> str:
    """Extract the family/primary name from entity name.

    'Walton Family Holdings' → 'Walton'
    'Bill & Melinda Gates Foundation' → 'Gates'
    'Koch Industries' → 'Koch'
    """
    # Remove common suffixes
    cleaned = entity_name
    for suffix in [" Family Office", " Family Holdings", " Capital",
                   " Management", " Investments", " Partners", " Group",
                   " Holdings", " Industries", " LLC", " LP", " Inc",
                   " Ltd", " Advisors", " Advisory", " Enterprises",
                   " Ventures", " Trust"]:
        cleaned = re.sub(re.escape(suffix), "", cleaned, flags=re.IGNORECASE)

    # Try to get just the family surname
    parts = cleaned.strip().split()
    if len(parts) >= 1:
        # If format is "First Last" or just "Last"
        return parts[-1]  # Take last word as family name

    return cleaned.strip()


def _generate_search_terms(entity_name: str, family_name: str) -> List[str]:
    """Generate foundation search terms from entity and family names."""
    terms = []

    for pattern in FAMILY_FOUNDATION_PATTERNS:
        terms.append(pattern.format(name=entity_name, family=family_name))

    # Also try the raw name
    terms.append(entity_name)
    terms.append(family_name)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in terms:
        key = t.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


def _search_foundation(search_term: str) -> Optional[Dict]:
    """Search ProPublica Nonprofit Explorer for a foundation."""
    cache_key = search_term.lower().strip()
    if cache_key in _search_cache:
        return _search_cache[cache_key]

    try:
        url = "https://projects.propublica.org/nonprofits/api/v2/search.json"
        params = {"q": search_term}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            organizations = data.get("organizations", [])

            # Filter for private foundations (NTEE code T = Philanthropy)
            # or large organizations with matching names
            for org in organizations[:10]:
                org_name = org.get("name", "").lower()
                search_lower = search_term.lower()

                # Check name relevance
                if _foundation_name_match(search_term, org.get("name", "")):
                    # Prefer foundations (subsection 3 = private foundation)
                    _search_cache[cache_key] = org
                    return org

            # Fallback: take first result if name is close enough
            if organizations and _foundation_name_match(search_term, organizations[0].get("name", "")):
                _search_cache[cache_key] = organizations[0]
                return organizations[0]

        _search_cache[cache_key] = None
        return None

    except Exception as e:
        logger.debug(f"ProPublica search failed for '{search_term}': {e}")
        _search_cache[cache_key] = None
        return None


def _get_latest_filing(ein: int) -> Optional[Dict]:
    """Get the latest Form 990 filing for an organization."""
    try:
        url = f"https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            org = data.get("organization", {})
            filings = data.get("filings_with_data", [])

            if filings:
                # Return most recent filing
                return filings[0]

        return None

    except Exception as e:
        logger.debug(f"ProPublica filing fetch failed for EIN {ein}: {e}")
        return None


def _get_top_officer(officers: List[Dict]) -> Optional[Dict]:
    """Get the top-ranked officer from a 990 filing."""
    # Priority order for titles
    priority_titles = [
        "president", "chairman", "chair", "ceo", "chief executive",
        "executive director", "managing director", "trustee", "director",
        "treasurer", "secretary", "vice president",
    ]

    for priority in priority_titles:
        for officer in officers:
            title = (officer.get("title") or "").lower()
            if priority in title:
                return officer

    # Fallback: return first officer
    return officers[0] if officers else None


def _foundation_name_match(search_term: str, org_name: str) -> bool:
    """Check if organization name matches the search."""
    s = search_term.lower().strip()
    o = org_name.lower().strip()

    if s == o:
        return True

    # Search term words appear in org name
    search_words = set(s.split())
    org_words = set(o.split())

    # Remove common words
    stopwords = {"the", "of", "and", "for", "a", "an", "inc", "llc", "ltd", "corp"}
    search_significant = search_words - stopwords
    org_significant = org_words - stopwords

    if search_significant and search_significant.issubset(org_significant):
        return True

    # At least 60% word overlap
    if len(search_significant) > 1:
        overlap = len(search_significant & org_significant)
        if overlap / len(search_significant) >= 0.6:
            return True

    return False


def _format_assets(amount: int) -> str:
    """Format dollar amount to readable string."""
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}B"
    elif amount >= 1_000_000:
        return f"${amount / 1_000_000:.0f}M"
    elif amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    else:
        return f"${amount:,}"


def _state_code_to_name(code: str) -> str:
    """Convert US state code to full name."""
    names = {
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
        "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
        "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
        "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
        "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
        "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
        "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
        "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
        "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
        "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
        "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
        "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
        "WI": "Wisconsin", "WY": "Wyoming", "DC": "D.C.",
    }
    return names.get(code.upper(), code)
