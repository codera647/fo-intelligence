"""ProPublica Nonprofit Explorer discovery — finds family offices & foundations.

Two approaches:
  1. Direct search for "family office" (some orgs actually register as nonprofits)
  2. Search for large family foundations → infer family office existence

ProPublica API: free, no key, ~3 req/sec rate limit.
"""

import time
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "FO-Intelligence/1.0 (research@fo-intelligence.com)",
    "Accept": "application/json",
}

# Search terms — "family office" first (some orgs literally register that way)
SEARCH_TERMS = [
    "family office",
    "family foundation",
    "family charitable trust",
    "private foundation",
    "family fund",
    "family charitable foundation",
]

# Minimum total assets for foundation-derived candidates (not for direct FO matches)
MIN_ASSETS_FOUNDATION = 50_000_000


def search_propublica(max_results: int = 30) -> List[Dict]:
    """Search ProPublica for family offices and large family foundations.

    Returns list of candidate dicts: {name, website, notes, entity_type, source}
    """
    candidates = []
    seen_names = set()

    for term in SEARCH_TERMS:
        if len(candidates) >= max_results:
            break

        try:
            url = "https://projects.propublica.org/nonprofits/api/v2/search.json"
            params = {"q": term}
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)

            if resp.status_code != 200:
                logger.debug(f"ProPublica returned {resp.status_code} for '{term}'")
                continue

            data = resp.json()
            organizations = data.get("organizations", [])

            for org in organizations:
                name = org.get("name", "")
                if not name:
                    continue

                total_assets = org.get("total_assets", 0) or 0

                # Determine if this is a direct family office match or a foundation
                is_direct_fo = _is_direct_family_office(name)

                if is_direct_fo:
                    # Direct FO match — use as-is, no asset filter
                    fo_name = _clean_org_name(name)
                elif _looks_like_family_foundation(name):
                    # Foundation match — apply asset filter and derive FO name
                    if total_assets < MIN_ASSETS_FOUNDATION:
                        continue
                    fo_name = _foundation_to_fo_name(name)
                else:
                    continue

                if not fo_name:
                    continue

                # Dedup
                key = fo_name.lower().strip()
                if key in seen_names:
                    continue
                seen_names.add(key)

                city = org.get("city", "")
                state = org.get("state", "")
                location = f"{city}, {state}" if city and state else city or state

                notes = f"From ProPublica: {name}"
                if total_assets > 0:
                    notes += f" (assets: ${total_assets:,.0f})"
                if location:
                    notes += f" in {location}"

                candidates.append({
                    "name": fo_name,
                    "website": None,
                    "notes": notes,
                    "entity_type": "Single Family Office",
                    "source": "propublica",
                    "hq_city": city.title() if city else None,
                    "hq_state": state if state else None,
                    "hq_country": "United States of America" if state else None,
                })

                if len(candidates) >= max_results:
                    break

            time.sleep(0.5)

        except Exception as e:
            logger.warning(f"ProPublica search failed for '{term}': {e}")
            continue

    logger.info(f"ProPublica discovery: {len(candidates)} family office candidates")
    return candidates


def _is_direct_family_office(name: str) -> bool:
    """Check if the organization name directly contains 'family office'."""
    return "family office" in name.lower()


def _clean_org_name(name: str) -> str:
    """Clean up an org name that is already a family office."""
    name = name.strip()
    # Remove corporate suffixes
    for suffix in [" Inc", " Inc.", " LLC", " Ltd", " Corp", " Corporation",
                   " Incorporated", " Co", " Co."]:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def _looks_like_family_foundation(name: str) -> bool:
    """Check if the foundation name suggests a family connection.

    STRICT: requires the word 'family' or 'personal' in the name.
    Short generic names like 'Smith Foundation' are too ambiguous.
    """
    name_lower = name.lower()

    # Must have an explicit family/personal signal
    family_signals = ["family", "personal"]
    if not any(signal in name_lower for signal in family_signals):
        return False

    # And must also have a foundation-type word
    foundation_words = ["foundation", "trust", "fund", "charitable"]
    return any(w in name_lower for w in foundation_words)


def _foundation_to_fo_name(foundation_name: str) -> str:
    """Convert foundation name to likely family office name.

    'The Walton Family Foundation' → 'Walton Family Office'
    'Bill & Melinda Gates Foundation' → 'Gates Family Office'
    """
    name = foundation_name.strip()

    # Remove prefixes
    for prefix in ["The ", "THE "]:
        if name.startswith(prefix):
            name = name[len(prefix):]

    # Remove corporate suffixes
    for suffix in [" Inc", " Inc.", " LLC", " Ltd", " Corp", " Corporation",
                   " Incorporated"]:
        name = name.replace(suffix, "")

    # Remove foundation-type words
    for word in [" Foundation", " Charitable Trust", " Charitable Foundation",
                 " Family Foundation", " Family Trust", " Family Fund",
                 " Fund", " Trust", " Charity"]:
        name = name.replace(word, "")

    name = name.strip()
    if not name:
        return ""

    # Handle multi-person names
    if " & " in name or " and " in name.lower():
        parts = name.replace(" & ", " ").replace(" and ", " ").split()
        if parts:
            name = parts[-1]

    return f"{name} Family Office"
