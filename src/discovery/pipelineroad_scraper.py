"""
Stage 1: PipelineRoad Discovery
================================
Scrapes pipelineroad.com/directory/type/family-office for all ~130 family offices.

Two passes:
  1. Listing page  -> basic info (name, slug, location, AUM, asset classes)
  2. Detail pages   -> enriched info (website, description, investment strategy, etc.)

Output: data/pipeline/01_discovered_family_offices.json

Usage:
    python run_discovery.py
"""

import re
import json
import time
import logging
import requests
from bs4 import BeautifulSoup
from pathlib import Path

logger = logging.getLogger(__name__)

LISTING_URL = "https://pipelineroad.com/directory/type/family-office"
BASE_URL = "https://pipelineroad.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}

# Known asset class names (longest first for greedy matching)
KNOWN_ASSET_CLASSES = sorted([
    "Private Equity", "Real Estate", "Public Equities", "Hedge Funds",
    "Venture Capital", "Fixed Income", "Infrastructure", "Growth Equity",
    "Credit", "Commodities", "Equities", "Consumer Goods", "Banking",
    "Art and Collectibles", "Industrial Holdings", "Impact Investing",
    "Natural Resources", "Life Sciences", "Consumer Brands",
    "Distressed Debt", "Media and Entertainment", "Pharmaceuticals",
    "Energy", "Hospitality", "Agriculture", "Retail", "Shipping",
    "Sports and Entertainment", "Asset Management",
], key=len, reverse=True)


# ─── Listing Page ─────────────────────────────────────────────────

def scrape_listing_page() -> list[dict]:
    """Fetch the FO listing page and extract basic records for all FOs."""
    logger.info(f"Fetching listing page: {LISTING_URL}")
    resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Match /directory/SLUG (single segment, no /type/ prefix)
    slug_re = re.compile(r"^/directory/([a-z0-9][a-z0-9._-]+)$")

    records: list[dict] = []
    seen_slugs: set[str] = set()

    for a_tag in soup.find_all("a", href=slug_re):
        href = a_tag["href"]
        slug = slug_re.match(href).group(1)  # type: ignore[union-attr]

        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        text = a_tag.get_text(" ", strip=True)
        record = _parse_listing_text(text, slug)
        if record:
            records.append(record)

    logger.info(f"Extracted {len(records)} family offices from listing page")
    return records


def _parse_listing_text(text: str, slug: str) -> dict | None:
    """Parse the concatenated text of a listing entry into structured fields.

    Typical formats:
        "C Cascade Investment Family Office · Kirkland, WA AUM $70B Private EquityReal Estate +1"
        "A Advance Publications, Inc. Family Office · New York, New York Private EquityVenture Capital"
    """
    # Split on middle-dot separator
    parts = re.split(r"\s*[·•]\s*", text, maxsplit=1)
    name_part = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""

    # Strip leading initial letter (avatar icon): "C Cascade..." -> "Cascade..."
    name_cleaned = re.sub(r"^[A-Z]\s+", "", name_part)

    # Keep full name including "Family Office" for now; strip trailing whitespace
    name = name_cleaned.strip()
    if not name:
        return None

    # ── Parse the right half: location, AUM, asset classes ──
    aum_raw = None
    location = ""
    asset_classes: list[str] = []

    aum_match = re.search(r"AUM\s+\$([0-9,.]+[TBMK]?)", rest)
    if aum_match:
        aum_raw = "$" + aum_match.group(1)
        location = rest[: aum_match.start()].strip().rstrip(", ")
        asset_text = rest[aum_match.end() :].strip()
    else:
        # No AUM — split location from trailing asset classes
        asset_text = ""
        for ac in KNOWN_ASSET_CLASSES:
            if ac in rest:
                idx = rest.index(ac)
                asset_text = rest[idx:]
                location = rest[:idx].strip().rstrip(", ")
                break
        if not asset_text:
            location = rest

    # Parse concatenated asset classes
    if asset_text:
        asset_text = re.sub(r"\s*\+\d+\s*$", "", asset_text)  # strip "+3"
        asset_classes = _extract_asset_classes(asset_text)

    return {
        "name": name,
        "slug": slug,
        "type": "Family Office",
        "location": location,
        "aum": aum_raw,
        "asset_classes": asset_classes,
        "detail_url": f"{BASE_URL}/directory/{slug}",
        "website": None,
        "description": None,
        "aum_date": None,
        "alternatives_allocation": None,
        "headquarters": None,
        "investment_strategy": None,
        "source": "PipelineRoad",
        "discovery_confidence": "High",
        "crawl_status": "Pending",
    }


def _extract_asset_classes(text: str) -> list[str]:
    """Pull known asset-class names out of a concatenated string."""
    found: list[str] = []
    remaining = text
    for ac in KNOWN_ASSET_CLASSES:  # already sorted longest-first
        if ac in remaining:
            found.append(ac)
            remaining = remaining.replace(ac, "", 1)
    return found


# ─── Detail Page ──────────────────────────────────────────────────

def scrape_detail_page(slug: str) -> dict:
    """Fetch one detail page and return enriched fields."""
    url = f"{BASE_URL}/directory/{slug}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"  ✗ Failed to fetch {slug}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    result: dict = {}

    # ── Website URL (link with ↗ arrow) ──
    for a in soup.find_all("a", href=True):
        link_text = a.get_text(strip=True)
        href = a["href"]
        if "↗" in link_text and "pipelineroad" not in href:
            result["website"] = href.rstrip("/")
            break

    # ── Description (meta tag is the cleanest source) ──
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        result["description"] = meta["content"]

    # ── AUM ──
    m = re.search(r"Assets Under Management\s+\$([0-9,.]+[TBMK]?)", full_text)
    if m:
        result["aum"] = "$" + m.group(1)

    # ── AUM date ──
    m = re.search(r"As of\s+(\d{4}-\d{2}-\d{2})", full_text)
    if m:
        result["aum_date"] = m.group(1)

    # ── Alternatives allocation ──
    m = re.search(r"Alternatives Allocation\s+(\d+)%", full_text)
    if m:
        result["alternatives_allocation"] = int(m.group(1))

    # ── Headquarters (between "Headquarters" and "Asset Classes") ──
    m = re.search(r"Headquarters\s+(.+?)\s+Asset Classes", full_text)
    if m:
        result["headquarters"] = m.group(1).strip()

    # ── Investment Strategy section ──
    strategy = _extract_section(soup, "Investment Strategy")
    if strategy:
        result["investment_strategy"] = strategy

    # ── Private Markets Approach section ──
    pm = _extract_section(soup, "Private Markets Approach")
    if pm:
        result["private_markets_approach"] = pm

    return result


def _extract_section(soup: BeautifulSoup, heading: str) -> str | None:
    """Grab all <p> text beneath an <h2> until the next heading."""
    for h2 in soup.find_all("h2"):
        if heading.lower() in h2.get_text(strip=True).lower():
            paragraphs: list[str] = []
            for sib in h2.find_next_siblings():
                if sib.name in ("h1", "h2"):
                    break
                if sib.name == "p":
                    paragraphs.append(sib.get_text(strip=True))
            return " ".join(paragraphs) if paragraphs else None
    return None


# ─── Orchestrator ─────────────────────────────────────────────────

def run_pipelineroad_discovery(output_path: Path) -> list[dict]:
    """Full Stage 1: listing page → detail pages → JSON.

    Supports resuming: if output_path already exists, FOs whose
    crawl_status != "Pending" are skipped.
    """
    logger.info("=" * 60)
    logger.info("STAGE 1: PipelineRoad Discovery")
    logger.info("=" * 60)

    # Phase 1 — listing page
    records = scrape_listing_page()

    # Check for existing progress
    already_done: set[str] = set()
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        # Build a map of slug → existing enriched record
        existing_map = {r["slug"]: r for r in existing}
        for rec in records:
            if rec["slug"] in existing_map:
                old = existing_map[rec["slug"]]
                if old.get("crawl_status") == "Discovered":
                    # Already processed — merge old data
                    rec.update({k: v for k, v in old.items() if v is not None})
                    already_done.add(rec["slug"])
        if already_done:
            logger.info(f"Resuming — {len(already_done)} FOs already processed")

    # Phase 2 — detail pages
    to_process = [r for r in records if r["slug"] not in already_done]
    logger.info(f"Fetching detail pages for {len(to_process)} family offices...")

    for i, record in enumerate(to_process):
        slug = record["slug"]
        logger.info(f"  [{i+1}/{len(to_process)}] {record['name']}")

        detail = scrape_detail_page(slug)

        # Merge — only overwrite if detail has a value
        for key, val in detail.items():
            if val is not None:
                record[key] = val

        record["crawl_status"] = "Discovered"

        # Incremental save every 10
        if (i + 1) % 10 == 0:
            _save_json(records, output_path)
            logger.info(f"  >> Progress saved ({i+1}/{len(to_process)})")

        time.sleep(1.0)  # polite rate limit

    # Final save
    _save_json(records, output_path)

    # Stats
    total = len(records)
    w_web = sum(1 for r in records if r.get("website"))
    w_aum = sum(1 for r in records if r.get("aum"))
    w_strat = sum(1 for r in records if r.get("investment_strategy"))
    w_hq = sum(1 for r in records if r.get("headquarters"))

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Discovery complete: {total} family offices")
    logger.info(f"  With website URL : {w_web}")
    logger.info(f"  With AUM         : {w_aum}")
    logger.info(f"  With HQ          : {w_hq}")
    logger.info(f"  With strategy    : {w_strat}")
    logger.info(f"  Saved to         : {output_path}")
    logger.info("=" * 60)

    return records


def _save_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
