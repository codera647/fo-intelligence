"""SEC EDGAR discovery — Channel 2.

Searches EDGAR full-text search (EFTS) for family office / investment adviser filings.
Free API, no key needed. Requires User-Agent header with contact info.
Rate limit: 10 req/sec.
"""

import time
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

# EDGAR full-text search API
EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
# Backup: structured search
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

HEADERS = {
    "User-Agent": "FO-Intelligence/1.0 (research@fo-intelligence.com)",
    "Accept": "application/json",
}


def search_sec_edgar(max_results: int = 40) -> List[Dict]:
    """Search SEC EDGAR for family office related filings.

    Targets Form ADV (investment adviser registration), 13F-HR (quarterly holdings),
    and Form D (private fund) filings.
    """
    candidates = []

    queries = [
        '"family office"',
        '"single family office"',
        '"multi family office"',
        '"family office" "investment adviser"',
    ]

    for query in queries:
        try:
            results = _search_efts(query, max_per_query=20)
            candidates.extend(results)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"EDGAR EFTS search failed for '{query}': {e}")

    # Try company tickers JSON as fallback
    if len(candidates) < 5:
        try:
            ticker_results = _search_company_tickers()
            candidates.extend(ticker_results)
        except Exception as e:
            logger.warning(f"EDGAR company tickers search failed: {e}")

    # Deduplicate by company name
    seen = set()
    unique = []
    for c in candidates:
        name_key = c["name"].lower().strip()
        if name_key not in seen and len(name_key) > 3:
            seen.add(name_key)
            unique.append(c)

    logger.info(f"SEC EDGAR discovered {len(unique)} unique candidates")
    return unique[:max_results]


def _search_efts(query: str, max_per_query: int = 20) -> List[Dict]:
    """Use EDGAR full-text search system (EFTS)."""
    params = {
        "q": query,
        "dateRange": "custom",
        "startdt": "2020-01-01",
        "enddt": "2026-12-31",
        "forms": "ADV,13F-HR,D",
    }

    try:
        resp = requests.get(EDGAR_EFTS_URL, params=params, headers=HEADERS, timeout=15)

        if resp.status_code != 200:
            logger.warning(f"EFTS returned {resp.status_code}")
            return []

        data = resp.json()
        results = []

        # Handle different response formats
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            hits = data.get("results", [])

        for hit in hits[:max_per_query]:
            source = hit.get("_source", hit)
            name = (
                source.get("entity_name")
                or source.get("display_names", [""])[0]
                or source.get("company_name", "")
            )

            if name and _is_likely_family_office(name):
                form_type = source.get("form_type", source.get("forms", "Unknown"))
                results.append({
                    "name": _clean_name(name),
                    "website": None,
                    "notes": f"SEC EDGAR: {form_type} filing",
                    "entity_type": "Unknown",
                    "source": "sec_edgar",
                    "cik": source.get("entity_id") or source.get("cik"),
                })

        return results

    except Exception as e:
        logger.warning(f"EFTS search error: {e}")
        return []


def _search_company_tickers() -> List[Dict]:
    """Fallback: search SEC company tickers JSON for FO-related names."""
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []

        for key, entry in data.items():
            name = entry.get("title", "")
            if name and _is_likely_family_office(name):
                results.append({
                    "name": _clean_name(name),
                    "website": None,
                    "notes": f"SEC registered: CIK {entry.get('cik_str', '')}",
                    "entity_type": "Unknown",
                    "source": "sec_edgar",
                    "cik": str(entry.get("cik_str", "")),
                })

        return results[:30]  # Cap at 30

    except Exception as e:
        logger.warning(f"Company tickers search failed: {e}")
        return []


def _is_likely_family_office(name: str) -> bool:
    """Filter for likely family office entities.

    STRICT: requires the word 'family' in the name combined with an
    investment-related term.  Generic finance words like 'capital',
    'investment', 'wealth' alone are NOT enough — they match thousands
    of hedge funds, RIAs, and PE firms.
    """
    name_lower = name.lower()

    # Negative signals — reject immediately
    exclude = [
        "bank", "insurance", "mutual fund", "etf", "index fund",
        "savings", "credit union", "exchange", "securities commission",
        "regulatory", "association", "committee", "sovereign",
    ]
    if any(kw in name_lower for kw in exclude):
        return False

    # Must contain 'family' + an investment-related word
    if "family" not in name_lower:
        return False

    fo_companions = [
        "office", "capital", "investment", "investments", "wealth",
        "trust", "partners", "holdings", "ventures", "management",
        "fund", "advisors", "advisory", "group", "equity",
    ]
    return any(word in name_lower for word in fo_companions)


def _clean_name(name: str) -> str:
    """Clean entity name from SEC filings."""
    # Remove common SEC suffixes
    name = name.strip()
    for suffix in ["/ADV", "/A", " (Filer)", " (Subject)"]:
        name = name.replace(suffix, "")
    # Title case if all caps
    if name.isupper():
        name = name.title()
    return name.strip()
