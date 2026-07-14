"""SEC EDGAR enrichment — pulls structured data from company filings.

Uses the EDGAR submissions API (data.sec.gov) to extract:
  - Registered address (city, state, country)
  - SIC code → investment sectors
  - Filing history (Form ADV, 13F, D) → recent activity
  - Entity category

CIK lookup uses two methods:
  1. Direct passthrough from discovery (if candidate was found via EDGAR)
  2. EDGAR company search HTML parsing (cgi-bin/browse-edgar)
"""

import re
import time
import logging
import requests
from typing import Dict, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "FO-Intelligence/1.0 (research@fo-intelligence.com)",
    "Accept-Encoding": "gzip, deflate",
}

# Cache CIK lookups
_cik_cache: Dict[str, Optional[str]] = {}


def enrich_from_edgar(name: str, existing_data: Dict, cik: str = None) -> Dict:
    """Enrich a family office record using SEC EDGAR filing data.

    Args:
        name: Entity name
        existing_data: Current record fields
        cik: Pre-known CIK from discovery (skips lookup if provided)

    Returns dict of fields to merge (only non-empty values).
    """
    result = {}

    try:
        # Step 1: Get CIK
        if not cik:
            cik = _find_cik(name)
        if not cik:
            return {}

        time.sleep(0.3)

        # Step 2: Get company info from EDGAR submissions API
        company_data = _get_company_info(cik)
        if not company_data:
            return {}

        # Step 3: Extract structured fields
        # Address
        addresses = company_data.get("addresses", {})
        addr = addresses.get("business", {}) or addresses.get("mailing", {})

        if addr:
            city = addr.get("city", "")
            state = addr.get("stateOrCountry", "")

            if city and not existing_data.get("hq_city"):
                result["hq_city"] = city.title()

            if state and not existing_data.get("hq_state"):
                result["hq_state"] = _state_code_to_name(state)

            if not existing_data.get("hq_country"):
                if state and len(state) == 2 and state.upper() in US_STATE_CODES:
                    result["hq_country"] = "United States of America"

            street = addr.get("street1", "")
            if street and not existing_data.get("hq_street_address"):
                street2 = addr.get("street2", "")
                full_street = f"{street} {street2}".strip() if street2 else street
                result["hq_street_address"] = full_street.title()

        # Phone number from SEC filing
        phone = company_data.get("phone", "")
        if phone and not existing_data.get("contact_phone"):
            result["contact_phone"] = phone

        # SIC code → sector mapping
        sic_desc = company_data.get("sicDescription", "")
        if sic_desc and not existing_data.get("investing_sectors"):
            result["investing_sectors"] = _sic_to_sectors(sic_desc)

        # Filing history → recent activity
        filings = company_data.get("filings", {}).get("recent", {})
        if filings:
            forms = filings.get("form", [])
            dates = filings.get("filingDate", [])

            for i, form in enumerate(forms[:15]):
                if form in ("ADV", "ADV/A", "13F-HR", "13F-HR/A", "D", "D/A"):
                    if i < len(dates) and not existing_data.get("recent_activity"):
                        result["recent_activity"] = f"SEC {form} filing on {dates[i]}"
                        result["activity_date"] = dates[i]
                        result["activity_source_url"] = (
                            f"https://www.sec.gov/cgi-bin/browse-edgar?"
                            f"action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=10"
                        )
                    break

        if result:
            logger.info(f"EDGAR enriched {len(result)} fields for {name} (CIK: {cik})")

        return result

    except Exception as e:
        logger.warning(f"EDGAR enrichment failed for {name}: {e}")
        return {}


def _find_cik(name: str) -> Optional[str]:
    """Find SEC CIK number for an entity by name.

    Uses the EDGAR company search HTML page (most reliable method).
    """
    cache_key = name.lower().strip()
    if cache_key in _cik_cache:
        return _cik_cache[cache_key]

    # Method 1: EDGAR company search (HTML parsing)
    try:
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "company": name,
            "CIK": "",
            "type": "",  # Search all form types
            "dateb": "",
            "owner": "include",
            "count": "10",
            "search_text": "",
            "action": "getcompany",
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for company results table
            table = soup.find("table", class_="tableFile2")
            if table:
                rows = table.find_all("tr")[1:]  # Skip header
                for row in rows[:5]:
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        cik_link = cols[0].find("a")
                        company_name = cols[1].get_text(strip=True)

                        if cik_link and _name_match(name, company_name):
                            # Extract CIK from link href
                            href = cik_link.get("href", "")
                            cik_match = re.search(r'CIK=(\d+)', href)
                            if cik_match:
                                cik = cik_match.group(1)
                                _cik_cache[cache_key] = cik
                                logger.debug(f"Found CIK {cik} for '{name}' via browse-edgar")
                                return cik

                            # Or CIK might be the text content
                            cik_text = cik_link.get_text(strip=True)
                            if cik_text.isdigit():
                                _cik_cache[cache_key] = cik_text
                                logger.debug(f"Found CIK {cik_text} for '{name}' via browse-edgar")
                                return cik_text

    except Exception as e:
        logger.debug(f"Browse-edgar search failed for '{name}': {e}")

    time.sleep(0.3)

    # Method 2: Company tickers JSON (fallback, only public companies)
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for key, entry in data.items():
                if _name_match(name, entry.get("title", "")):
                    cik = str(entry.get("cik_str", ""))
                    if cik:
                        _cik_cache[cache_key] = cik
                        logger.debug(f"Found CIK {cik} for '{name}' via company_tickers")
                        return cik
    except Exception:
        pass

    _cik_cache[cache_key] = None
    return None


def _get_company_info(cik: str) -> Optional[Dict]:
    """Get company info from EDGAR submissions API."""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        logger.debug(f"EDGAR submissions returned {resp.status_code} for CIK {cik}")
        return None
    except Exception as e:
        logger.debug(f"Failed to get company info for CIK {cik}: {e}")
        return None


def _name_match(search_name: str, found_name: str) -> bool:
    """Check if two entity names are a reasonable match."""
    s = _strip_suffixes(search_name.lower().strip())
    f = _strip_suffixes(found_name.lower().strip())

    if s == f:
        return True
    if s in f or f in s:
        return True

    # Word overlap check
    s_words = set(s.split())
    f_words = set(f.split())
    if len(s_words) > 1 and len(s_words & f_words) >= len(s_words) * 0.6:
        return True

    return False


def _strip_suffixes(name: str) -> str:
    """Remove common corporate suffixes."""
    for suffix in [" llc", " lp", " inc", " inc.", " ltd", " corp", " corp.",
                   " co", " co.", " group", " holdings", " management",
                   " partners", " advisors", " capital", " family office"]:
        name = name.replace(suffix, "")
    return name.strip()


def _state_code_to_name(code: str) -> str:
    """Convert US state code to full name."""
    return US_STATE_NAMES.get(code.upper(), code)


def _sic_to_sectors(sic_desc: str) -> str:
    """Map SIC description to investment sectors."""
    desc_lower = sic_desc.lower()
    sectors = []

    if any(w in desc_lower for w in ["invest", "security", "fund", "asset"]):
        sectors.extend(["Private Equity", "Public Equities", "Direct Investments"])
    if any(w in desc_lower for w in ["real estate", "property"]):
        sectors.append("Real Estate")
    if any(w in desc_lower for w in ["bank", "finance", "credit"]):
        sectors.append("Financial Services")
    if any(w in desc_lower for w in ["tech", "software", "computer"]):
        sectors.append("Technology")
    if any(w in desc_lower for w in ["health", "pharma", "bio"]):
        sectors.append("Healthcare")
    if any(w in desc_lower for w in ["oil", "gas", "energy", "petrol"]):
        sectors.append("Energy")

    return ", ".join(sectors) if sectors else "Diversified Investments"


US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU",
}

US_STATE_NAMES = {
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
