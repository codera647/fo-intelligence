"""Orchestrates all discovery channels → deduplicated, filtered candidate list.

4 channels:
  1. Curated seed list (~65+ known FOs)
  2. SEC EDGAR filings (~30-40 additional)
  3. Brave web search (~20-30 additional)
  4. ProPublica Nonprofit Explorer (~15-25 additional)

Post-discovery:
  - Deduplicate by normalized name
  - Filter: must have working website OR SEC filing
  - Rank by source reliability
"""

import time
import logging
import requests
from typing import List, Dict
from .seed_list import SEED_FAMILY_OFFICES
from .sec_edgar import search_sec_edgar
from .web_search import search_google_news, search_for_website
from .propublica_discovery import search_propublica

logger = logging.getLogger(__name__)


def run_discovery(target_candidates: int = 100) -> List[Dict]:
    """Run all discovery channels and merge into a deduplicated candidate list.

    Pipeline:
      1. Curated seed list (~65 known FOs)
      2. SEC EDGAR search (~30-40 additional)
      3. Web search (~20-30 additional)
      4. ProPublica nonprofit search (~15-25 additional)
      5. Deduplicate by normalized name
      6. Pre-enrichment filter (website or SEC filing required)
      7. Return ranked candidates

    Returns list of dicts with keys: name, website, notes, entity_type, source
    """
    all_candidates = []

    # ── Channel 1: Seed list ───────────────────────────────────────
    logger.info("Channel 1: Loading curated seed list...")
    for seed in SEED_FAMILY_OFFICES:
        candidate = {
            "name": seed["name"],
            "website": seed.get("website"),
            "notes": seed.get("notes", ""),
            "entity_type": seed.get("entity_type", "Unknown"),
            "source": "seed_list",
        }
        # Carry forward pre-filled enrichment data from seed
        for extra_field in ["hq_city", "hq_state", "hq_country", "description"]:
            if seed.get(extra_field):
                candidate[extra_field] = seed[extra_field]
        all_candidates.append(candidate)
    logger.info(f"  Seed list: {len(SEED_FAMILY_OFFICES)} candidates")

    # ── Channel 2: SEC EDGAR ───────────────────────────────────────
    logger.info("Channel 2: Searching SEC EDGAR...")
    try:
        edgar_results = search_sec_edgar(max_results=40)
        all_candidates.extend(edgar_results)
        logger.info(f"  SEC EDGAR: {len(edgar_results)} candidates")
    except Exception as e:
        logger.warning(f"  SEC EDGAR failed: {e}")

    # ── Channel 3: Web / News search ──────────────────────────────
    logger.info("Channel 3: Searching web/news...")
    try:
        news_results = search_google_news(max_results=30)
        all_candidates.extend(news_results)
        logger.info(f"  Web search: {len(news_results)} candidates")
    except Exception as e:
        logger.warning(f"  Web search failed: {e}")

    # ── Channel 4: ProPublica Nonprofit Explorer ──────────────────
    logger.info("Channel 4: Searching ProPublica nonprofits...")
    try:
        propublica_results = search_propublica(max_results=25)
        all_candidates.extend(propublica_results)
        logger.info(f"  ProPublica: {len(propublica_results)} candidates")
    except Exception as e:
        logger.warning(f"  ProPublica failed: {e}")

    logger.info(f"Total raw candidates: {len(all_candidates)}")

    # ── Deduplicate ────────────────────────────────────────────────
    unique = _deduplicate(all_candidates)
    logger.info(f"After dedup: {len(unique)} unique candidates")

    # ── Pre-enrichment filter ──────────────────────────────────────
    logger.info("Running pre-enrichment filter (website or SEC filing required)...")
    filtered = _pre_enrichment_filter(unique)
    logger.info(f"After filter: {len(filtered)} enrichable candidates (from {len(unique)})")

    # ── Rank: prefer seed > edgar > propublica > web_search ───────
    source_priority = {"seed_list": 0, "sec_edgar": 1, "propublica": 2, "web_search": 3}
    filtered.sort(key=lambda c: source_priority.get(c.get("source", ""), 4))

    return filtered[:target_candidates]


def _pre_enrichment_filter(candidates: List[Dict]) -> List[Dict]:
    """Filter candidates before enrichment to avoid wasting LLM calls.

    A candidate passes if it has:
      - A pre-existing website URL (from seed list or discovery), OR
      - Came from SEC EDGAR (has verified SEC filing), OR
      - Came from seed list (curated = trustworthy), OR
      - We can quickly find a website for it via search

    Candidates with none of the above are dropped.
    """
    passed = []

    for candidate in candidates:
        # Auto-pass: seed list entries (curated, reliable)
        if candidate.get("source") == "seed_list":
            passed.append(candidate)
            continue

        # Auto-pass: SEC EDGAR entries (have verified filing)
        if candidate.get("source") == "sec_edgar":
            passed.append(candidate)
            continue

        # Auto-pass: has a website already
        if candidate.get("website"):
            passed.append(candidate)
            continue

        # For others (web search, ProPublica): try to find a website
        name = candidate.get("name", "")
        if name:
            try:
                website = search_for_website(name)
                if website:
                    candidate["website"] = website
                    passed.append(candidate)
                    time.sleep(0.3)
                    continue
            except Exception:
                pass

        # No verifiable source → skip
        logger.debug(f"  Filtered out (no verifiable source): {candidate.get('name')}")

    return passed


def _deduplicate(candidates: List[Dict]) -> List[Dict]:
    """Deduplicate candidates by normalized name, keeping the richest record."""
    seen: Dict[str, Dict] = {}

    for c in candidates:
        key = _normalize_name(c["name"])
        if key in seen:
            # Merge: keep existing but fill in blanks
            existing = seen[key]
            if not existing.get("website") and c.get("website"):
                existing["website"] = c["website"]
            if not existing.get("notes") and c.get("notes"):
                existing["notes"] = c["notes"]
            if existing.get("entity_type") == "Unknown" and c.get("entity_type") != "Unknown":
                existing["entity_type"] = c["entity_type"]
            # Merge extra fields
            for field in ["hq_city", "hq_state", "hq_country", "description"]:
                if not existing.get(field) and c.get(field):
                    existing[field] = c[field]
        else:
            seen[key] = c.copy()

    return list(seen.values())


def _normalize_name(name: str) -> str:
    """Normalize entity name for dedup matching."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [", llc", ", lp", ", inc", " llc", " lp", " inc", " inc.",
                   " ltd", " limited", " family office"]:
        name = name.replace(suffix, "")
    # Remove extra whitespace
    name = " ".join(name.split())
    return name
