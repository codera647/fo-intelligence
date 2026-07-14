"""Web search discovery — Channel 3.

Uses Brave Search API (free tier: 2,000 queries/month) for reliable, structured results.
"""

import time
import re
import logging
import requests
from typing import List, Dict, Optional

from config.settings import BRAVE_API_KEY

logger = logging.getLogger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _brave_search(query: str, max_results: int = 10) -> List[Dict]:
    """Execute a Brave Search API query and return structured results."""
    if not BRAVE_API_KEY:
        logger.warning("BRAVE_API_KEY not set — skipping web search")
        return []

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": min(max_results, 20),
        "safesearch": "off",
    }

    try:
        resp = requests.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=15)

        if resp.status_code == 429:
            logger.warning("Brave Search rate-limited (429) — backing off 5s")
            time.sleep(5)
            resp = requests.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=15)

        if resp.status_code != 200:
            logger.warning(f"Brave Search returned {resp.status_code}: {resp.text[:200]}")
            return []

        data = resp.json()
        web_results = data.get("web", {}).get("results", [])

        results = []
        for r in web_results[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "text": f"{r.get('title', '')} {r.get('description', '')}",
                "url": r.get("url", ""),
                "source": "web_search",
            })

        return results

    except requests.exceptions.Timeout:
        logger.debug(f"Brave Search timeout for: {query[:50]}")
        return []
    except Exception as e:
        logger.warning(f"Brave Search request failed: {e}")
        return []


def search_google_news(max_results: int = 30) -> List[Dict]:
    """Search for recently active family offices using Brave Search API."""
    candidates = []

    search_queries = [
        "family office investment 2024 2025",
        "single family office technology AI investment",
        "multi family office wealth management",
        "family office real estate private equity fund",
        "family office venture capital startup funding",
        "family office healthcare biotech",
        "new family office launch",
        "family office direct investment",
    ]

    consecutive_failures = 0

    for query in search_queries:
        if consecutive_failures >= 3:
            logger.warning("Brave Search failing consecutively — skipping remaining discovery queries")
            break

        try:
            results = _brave_search(query, max_results=10)
            if results:
                consecutive_failures = 0
                for r in results:
                    parsed = _parse_search_result(r)
                    if parsed:
                        candidates.append(parsed)
            else:
                consecutive_failures += 1

            # Brief delay between queries to stay well within rate limits
            time.sleep(1.0)

        except Exception as e:
            logger.warning(f"Web search failed for '{query}': {e}")
            consecutive_failures += 1
            continue

    # Deduplicate
    seen = set()
    unique = []
    for c in candidates:
        key = c["name"].lower().strip()
        if key not in seen and len(key) > 3:
            seen.add(key)
            unique.append(c)

    logger.info(f"Web search discovered {len(unique)} unique candidates")
    return unique[:max_results]


def _parse_search_result(result: Dict) -> Optional[Dict]:
    """Try to extract a family office name from a search result."""
    text = result.get("text", "")
    title = result.get("title", "")
    combined = f"{title} {text}"

    if not combined.strip():
        return None

    # STRICT: Only match patterns that contain "Family" — generic finance
    # names like "Capital Management" match thousands of non-FO entities.
    patterns = [
        r'([A-Z][a-zA-Z\s&\'-]+(?:Family Office|Family\s+Office))',
        r'([A-Z][a-zA-Z\s&\'-]+(?:Family Fund|Family Ventures|Family Holdings))',
        r'([A-Z][a-zA-Z\s&\'-]+(?:Family Capital|Family Investment|Family Wealth))',
        r'([A-Z][a-zA-Z\s&\'-]+(?:Family Partners|Family Trust|Family Management))',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, combined)
        for match in matches:
            name = match.strip()
            if 5 < len(name) < 60 and not _is_generic_phrase(name):
                return {
                    "name": name,
                    "website": None,
                    "notes": f"Found in web search: {title[:80]}",
                    "entity_type": "Unknown",
                    "source": "web_search",
                }

    return None


def _is_generic_phrase(name: str) -> bool:
    """Filter out generic phrases that aren't actual entity names."""
    generic = [
        "The Family Office", "A Family Office", "Family Office Network",
        "Family Office Investment", "Family Office Management",
        "Investment Management", "Wealth Management",
        "Capital Management", "Capital Group",
        "Best Family Office", "Top Family Office",
    ]
    return name.strip() in generic


def search_for_website(name: str) -> Optional[str]:
    """Find a family office's official website via Brave Search with validation.

    Uses multiple query strategies and scores candidates by how well the
    search-result text confirms the URL actually belongs to this entity.
    """
    from urllib.parse import urlparse

    # Build several query variants — the quoted-name query alone often
    # returns SEO-farm or same-word-different-company results.
    queries = [
        f'"{name}" official site',
        f'"{name}" family office',
        f'{name} website',
    ]

    scored_candidates: List[Dict] = []
    seen_domains: set = set()

    for query in queries:
        try:
            results = _brave_search(query, max_results=5)
        except Exception:
            continue

        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            if not _passes_domain_excludes(url):
                continue

            # De-dup by registered domain
            try:
                domain = urlparse(url).netloc.lower().replace("www.", "")
            except Exception:
                continue
            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            score = _score_website_candidate(
                url, domain, r.get("title", ""), r.get("text", ""), name
            )
            if score > 0:
                scored_candidates.append({"url": url, "score": score})

        time.sleep(0.5)

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    best = scored_candidates[0]

    # Require a minimum confidence before accepting
    if best["score"] < 15:
        return None

    # Normalise to homepage
    try:
        parsed = urlparse(best["url"])
        homepage = f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        homepage = best["url"]

    logger.info(f"Website found for '{name}': {homepage} (score={best['score']})")
    return homepage


def _passes_domain_excludes(url: str) -> bool:
    """Return False if the URL belongs to a directory / social / news site."""
    url_lower = url.lower()
    excludes = [
        "linkedin.com", "facebook.com", "twitter.com", "crunchbase.com",
        "bloomberg.com", "reuters.com", "wikipedia.org", "sec.gov",
        "youtube.com", "google.com", "duckduckgo.com", "bing.com",
        "pitchbook.com", "owler.com", "zoominfo.com", "brave.com",
        "instagram.com", "glassdoor.com", "indeed.com", "yelp.com",
        "dnb.com", "bbb.org", "manta.com", "mapquest.com",
        "yellowpages.com", "whitepages.com", "opencorporates.com",
        "apollo.io", "rocketreach.co", "fundz.net", "wealthx.com",
    ]
    return not any(ex in url_lower for ex in excludes)


def _score_website_candidate(
    url: str, domain: str, title: str, snippet: str, name: str
) -> int:
    """Score how likely *url* is the official site of *name*.

    Scoring signals (additive):
      - Domain contains the entity's distinctive words      → up to 30
      - Search title / snippet contains the full entity name → 25
      - Domain is short (< 25 chars, likely a real homepage) → 5
      - Title/snippet contains "family office" or similar    → 10
    Penalties:
      - Domain word matched but it's a generic finance word  → −15
      - URL is a sub-page deeper than /about or /team        → −5
    """
    score = 0
    domain_lower = domain.lower()
    combined = f"{title} {snippet}".lower()

    # ── Which name-words are "distinctive" vs generic finance terms? ──
    generic_finance = {
        "investment", "investments", "capital", "group", "management",
        "partners", "holdings", "fund", "funds", "family", "office",
        "advisors", "advisory", "wealth", "asset", "assets", "private",
        "global", "international", "trust", "foundation", "ventures",
        "equity", "financial", "services", "company", "corporation",
        "llc", "inc", "ltd", "the",
    }
    name_words = [w.lower() for w in name.split() if len(w) > 2]
    distinctive = [w for w in name_words if w not in generic_finance]
    generic_matched = [w for w in name_words if w in generic_finance]

    # ── Signal 1: Domain contains distinctive name words ─────────────
    # Strip TLD for matching (e.g. "cascadeassetmanagement.com" → "cascadeassetmanagement")
    domain_stem = domain_lower.split(".")[0]

    distinctive_in_domain = sum(1 for w in distinctive if w in domain_stem)
    if distinctive_in_domain >= 2:
        score += 30
    elif distinctive_in_domain == 1:
        # Single distinctive word is decent but not conclusive
        score += 18
    else:
        # Only generic words matched (e.g. "investment" in "cascadeinv")
        generic_in_domain = sum(1 for w in generic_matched if w in domain_stem)
        if generic_in_domain > 0:
            score += 3  # Very weak signal — "investment" appears in thousands of domains

    # ── Signal 2: Full entity name in title / snippet ────────────────
    name_lower = name.lower()
    if name_lower in combined:
        score += 25
    else:
        # Check if distinctive words appear together in the snippet
        if distinctive and all(w in combined for w in distinctive):
            score += 15
        elif distinctive and any(w in combined for w in distinctive):
            score += 8

    # ── Signal 3: Domain brevity (real homepages are short) ──────────
    if len(domain_lower) < 25:
        score += 5

    # ── Signal 4: Industry confirmation in snippet ───────────────────
    fo_keywords = ["family office", "wealth management", "private investment",
                   "investment office", "single family", "multi family"]
    if any(kw in combined for kw in fo_keywords):
        score += 10

    # ── Penalty: deep sub-pages are less likely to be homepages ──────
    from urllib.parse import urlparse as _up
    try:
        path = _up(url).path.strip("/")
        if path.count("/") > 1:
            score -= 5
    except Exception:
        pass

    return max(score, 0)
