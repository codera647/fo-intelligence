"""
Stage 2: Website Crawling (Crawl4AI — Smart Discovery)
=======================================================
Uses Crawl4AI's AsyncWebCrawler with a two-pass approach:

  Pass 1: Crawl the homepage, extract ALL navigation links
  Pass 2: Filter discovered links by keywords (team, people,
           leaders, about, contact, investments, etc.) and
           crawl the matching subpages

This handles sites where team pages are at /our-people,
/professionals, /our-leaders, or any non-standard path.

Crawl4AI uses real Chromium, so it:
  - Renders JavaScript-heavy sites
  - Captures icon-embedded links (LinkedIn icons, mailto icons)
  - Extracts all <a href="..."> regardless of content (text or image)

Tuned for 16GB RAM / i5-1135G7.

Install:
    pip install crawl4ai
    crawl4ai-setup          # installs Playwright browsers
"""

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher, SemaphoreDispatcher, RateLimiter

# UndetectedAdapter — deep-level anti-bot patches (Cloudflare, DataDome, Akamai)
# Graceful fallback if crawl4ai version doesn't include it
try:
    from crawl4ai import UndetectedAdapter
    HAS_UNDETECTED = True
except ImportError:
    HAS_UNDETECTED = False

logger = logging.getLogger(__name__)

# ─── Keywords to identify high-value subpages from nav links ────────
# Matched against the URL path AND link text (case-insensitive)
SUBPAGE_KEYWORDS = [
    # Team / People
    "team", "people", "leadership", "leaders", "staff",
    "professionals", "advisors", "principals", "partners",
    "management", "who-we-are", "our-firm", "bios",
    # About
    "about", "story", "history", "mission", "overview",
    # Contact
    "contact", "connect", "reach-us", "get-in-touch", "locations",
    # Investments
    "invest", "portfolio", "strategy", "approach", "philosophy",
    "holdings", "focus", "sectors", "criteria", "track-record",
    "what-we-do", "capabilities",
    # News / Recent Activity
    "news", "press", "blog", "insights", "updates", "announcements",
    "media", "publications", "articles", "events", "releases",
]

# Fallback hardcoded paths (tried only if homepage link discovery fails)
FALLBACK_PATHS = [
    "/about", "/about-us", "/team", "/our-team", "/people",
    "/contact", "/investments", "/portfolio",
]

# ─── Machine-tuned settings (16GB RAM, i5-1135G7) ──────────────────
PAGE_TIMEOUT = 15000             # 15s per page (milliseconds)
MAX_SUBPAGES = 6                 # max subpages to crawl per FO


def _score_link(href: str, text: str) -> int:
    """Score a link by how many keywords it matches. Higher = more relevant."""
    href_lower = href.lower()
    text_lower = (text or "").lower()
    score = 0
    for kw in SUBPAGE_KEYWORDS:
        if kw in href_lower:
            score += 2  # URL match is stronger signal
        if kw in text_lower:
            score += 1
    return score


def _discover_subpages(internal_links: list[dict], base_url: str) -> list[str]:
    """From homepage's internal links, find the best subpages to crawl.

    Scores each link by keyword relevance, deduplicates, and returns
    the top MAX_SUBPAGES URLs sorted by score.
    """
    base_parsed = urlparse(base_url)
    base_domain = base_parsed.netloc
    seen_paths = set()
    scored: list[tuple[int, str]] = []

    for link in internal_links:
        href = link.get("href", "")
        text = link.get("text", "")
        if not href:
            continue

        # Normalize
        if href.startswith("/"):
            href = f"{base_parsed.scheme}://{base_domain}{href}"
        elif not href.startswith("http"):
            continue

        # Must be same domain
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != base_domain:
            continue

        # Skip homepage, anchors, files, query-heavy URLs
        path = parsed.path.rstrip("/")
        if not path or path == "/" or path == base_parsed.path.rstrip("/"):
            continue
        if any(path.endswith(ext) for ext in [".pdf", ".jpg", ".png", ".zip", ".docx"]):
            continue
        if parsed.query:  # skip ?page=2 etc
            continue

        # Deduplicate by path
        if path in seen_paths:
            continue
        seen_paths.add(path)

        score = _score_link(href, text)
        if score > 0:
            scored.append((score, href))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: -x[0])
    return [url for _, url in scored[:MAX_SUBPAGES]]


def _extract_structured_markers(all_links: list[list[dict]]) -> str:
    """Extract emails, LinkedIn URLs, and social links from crawled link data.

    Crawl4AI renders the full DOM (including icon-wrapped links), so
    result.links captures <a href="mailto:..."> and <a href="linkedin...">
    even when they wrap an <img> or <svg> icon instead of text.
    """
    markers = []
    emails = set()
    linkedin_profiles = set()
    corporate_linkedin = None
    other_socials = set()

    for link_group in all_links:
        for link in link_group:
            href = link.get("href", "")
            if not href:
                continue

            # Emails (mailto: links — including icon-embedded ones)
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                if "@" in email and not email.startswith("@"):
                    emails.add(email)

            # LinkedIn profiles (icon or text links)
            elif "linkedin.com/in/" in href:
                clean = href.split("?")[0].rstrip("/")
                linkedin_profiles.add(clean)
            elif "linkedin.com/company/" in href:
                corporate_linkedin = href.split("?")[0].rstrip("/")

            # Twitter / X
            elif any(s in href for s in ["twitter.com/", "x.com/"]):
                clean = href.split("?")[0].rstrip("/")
                if clean.count("/") >= 3:  # has a username
                    other_socials.add(clean)

            # Facebook, Instagram
            elif any(s in href for s in ["facebook.com/", "instagram.com/"]):
                clean = href.split("?")[0].rstrip("/")
                other_socials.add(clean)

    # ── Build marker blocks ──
    if emails:
        markers.append("=== EXTRACTED_EMAILS ===")
        markers.extend(sorted(emails))
        markers.append("")

        # Pick best corporate email
        corporate_prefixes = ["info@", "contact@", "office@", "enquiries@",
                              "hello@", "general@", "admin@", "reception@"]
        corporate_emails = [e for e in emails
                           if any(e.startswith(p) for p in corporate_prefixes)]
        if corporate_emails:
            markers.append("=== CORPORATE_EMAIL ===")
            markers.append(corporate_emails[0])
            markers.append("")

    if corporate_linkedin:
        markers.append("=== CORPORATE_LINKEDIN ===")
        markers.append(corporate_linkedin)
        markers.append("")

    if linkedin_profiles:
        markers.append("=== LINKEDIN_PROFILES ===")
        markers.extend(sorted(linkedin_profiles))
        markers.append("")

    if other_socials:
        markers.append("=== OTHER_SOCIALS ===")
        markers.extend(sorted(other_socials))
        markers.append("")

    return "\n".join(markers)


def _extract_emails_from_text(text: str) -> set[str]:
    """Regex-extract emails from page markdown text as a safety net."""
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    return {m.lower() for m in re.findall(pattern, text)
            if not any(x in m for x in [".png", ".jpg", ".gif", ".svg", "example.com"])}


async def _httpx_fallback(url: str) -> Optional[str]:
    """Simple HTTP fallback for sites that block headless browsers.

    Many Akamai/Cloudflare-protected sites serve full HTML to plain
    HTTP clients — they only block browser-automation fingerprints.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0, headers=headers
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.text) > 200:
                # Strip HTML tags for a rough text version
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                # Remove scripts/styles
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    return text
    except Exception:
        pass
    return None


async def crawl_fo_website_async(
    crawler: AsyncWebCrawler,
    website_url: str,
    fo_name: str,
    run_config: CrawlerRunConfig,
) -> Optional[str]:
    """Crawl a single FO site using smart two-pass discovery.

    Pass 1: Crawl homepage → collect internal links + external links
    Pass 2: Score internal links by keyword relevance → crawl top matches
    """
    if not website_url:
        return None

    # Normalize
    if not website_url.startswith("http"):
        website_url = "https://" + website_url
    website_url = website_url.rstrip("/")

    combined_parts: list[str] = []
    all_links: list[list[dict]] = []
    crawled_urls: set[str] = set()

    # ══════════════════════════════════════════════════════════════
    # PASS 1: Homepage
    # ══════════════════════════════════════════════════════════════
    homepage_internal_links: list[dict] = []

    try:
        result = await crawler.arun(url=website_url, config=run_config)
        if result.success and result.markdown and len(result.markdown.strip()) > 50:
            combined_parts.append(f"=== PAGE: {website_url} ===\n{result.markdown}")
            crawled_urls.add(website_url)

            # Collect ALL links (internal for discovery, external for markers)
            if result.links:
                internal = result.links.get("internal", [])
                external = result.links.get("external", [])
                homepage_internal_links = internal
                all_links.append(internal + external)
        else:
            # Crawl4AI got blocked or empty — try httpx fallback
            logger.info(f"    Homepage blocked in browser, trying httpx fallback...")
            fallback_text = await _httpx_fallback(website_url)
            if fallback_text:
                combined_parts.append(f"=== PAGE: {website_url} ===\n{fallback_text}")
                crawled_urls.add(website_url)
                logger.info(f"    httpx fallback got {len(fallback_text):,} chars")
            else:
                logger.warning(f"    Homepage: no content (browser + httpx) for {fo_name}")
                return None
    except Exception as e:
        # Browser crashed/errored — try httpx fallback
        logger.info(f"    Browser error for {fo_name}, trying httpx fallback...")
        fallback_text = await _httpx_fallback(website_url)
        if fallback_text:
            combined_parts.append(f"=== PAGE: {website_url} ===\n{fallback_text}")
            crawled_urls.add(website_url)
            logger.info(f"    httpx fallback got {len(fallback_text):,} chars")
        else:
            logger.warning(f"    Homepage: no content (browser + httpx) for {fo_name}")
            return None

    # ══════════════════════════════════════════════════════════════
    # PASS 2: Discover and crawl relevant subpages
    # ══════════════════════════════════════════════════════════════
    subpage_urls = _discover_subpages(homepage_internal_links, website_url)

    # If discovery found nothing, try fallback hardcoded paths
    if not subpage_urls:
        logger.info(f"    No keyword-matched links found, trying fallback paths")
        for path in FALLBACK_PATHS:
            subpage_urls.append(website_url + path)

    pages_ok = 1  # homepage counts
    for url in subpage_urls:
        if url in crawled_urls:
            continue
        try:
            result = await crawler.arun(url=url, config=run_config)
            if result.success and result.markdown and len(result.markdown.strip()) > 50:
                combined_parts.append(f"=== PAGE: {url} ===\n{result.markdown}")
                crawled_urls.add(url)
                pages_ok += 1

                # Collect links from subpages too (more emails, LinkedIn, etc.)
                if result.links:
                    internal = result.links.get("internal", [])
                    external = result.links.get("external", [])
                    all_links.append(internal + external)
        except Exception:
            pass  # 404s and errors are expected — silently skip

        # Stop after enough pages
        if pages_ok >= MAX_SUBPAGES + 1:
            break

    logger.info(f"    {fo_name}: {pages_ok} pages crawled, "
                f"{len(subpage_urls)} subpages discovered")

    # ══════════════════════════════════════════════════════════════
    # Build final text
    # ══════════════════════════════════════════════════════════════
    final_text = "\n\n".join(combined_parts)

    # Structured markers from link data (catches icon-embedded links)
    markers = _extract_structured_markers(all_links)

    # Safety net: regex-extract emails from page text too
    text_emails = _extract_emails_from_text(final_text)
    if text_emails:
        # Add any emails not already in markers
        existing_marker = "=== EXTRACTED_EMAILS ==="
        if existing_marker not in markers:
            markers += f"\n{existing_marker}\n" + "\n".join(sorted(text_emails)) + "\n"

    if markers:
        final_text += "\n\n" + markers

    return final_text


async def crawl_all_websites_async(
    records: list[dict],
    already_crawled: set[str] | None = None,
) -> dict[str, str]:
    """Crawl all FO websites using Crawl4AI with smart subpage discovery.

    One shared Chromium instance — sequential per-FO to keep RAM safe
    on 16GB systems while still being much faster than requests+BS4
    (headless browser handles JS sites, parallel page loads, etc.)

    Args:
        records: List of FO records from 01_discovered.json
        already_crawled: Slugs to skip (resume support)

    Returns:
        Dict of {slug: crawled_text}
    """
    if already_crawled is None:
        already_crawled = set()

    to_crawl = [
        r for r in records
        if r.get("website") and r["slug"] not in already_crawled
    ]

    total_with_url = sum(1 for r in records if r.get("website"))
    logger.info(f"Websites to crawl: {len(to_crawl)} "
                f"(of {total_with_url} with URLs, {len(already_crawled)} already done)")

    if not to_crawl:
        return {}

    # ── Configure Crawl4AI (stealth to reduce anti-bot blocks) ──
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        enable_stealth=True,               # playwright-stealth fingerprint patches
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    )

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,       # always fetch fresh
        page_timeout=PAGE_TIMEOUT,
        wait_until="domcontentloaded",     # faster than "networkidle"
        simulate_user=True,                # random mouse moves / scrolls
        override_navigator=True,           # hide webdriver flag
        magic=True,                        # Crawl4AI anti-detection suite
    )

    results: dict[str, str] = {}

    # ═══════════════════════════════════════════════════════════════
    # TIER 1: Normal stealth browser (fast — shared Chromium instance)
    # ═══════════════════════════════════════════════════════════════
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for i, record in enumerate(to_crawl):
            slug = record["slug"]
            name = record["name"]
            url = record["website"]

            logger.info(f"[{i+1}/{len(to_crawl)}] {name} — {url}")

            text = await crawl_fo_website_async(crawler, url, name, run_config)

            if text:
                results[slug] = text
                logger.info(f"    Total: {len(text):,} chars")
            else:
                logger.warning(f"    No content from {name}")

            # Brief delay between FOs to reduce anti-bot triggers
            if i < len(to_crawl) - 1:
                await asyncio.sleep(1.5)

    tier1_success = len(results)
    logger.info(f"Tier 1 (stealth) complete: {tier1_success}/{len(to_crawl)} sites")

    # ═══════════════════════════════════════════════════════════════
    # TIER 2: UndetectedAdapter for blocked sites
    # Deep-level patches bypass Cloudflare, DataDome, Akamai CDP
    # Creates a separate browser instance per retry
    # ═══════════════════════════════════════════════════════════════
    blocked = [
        r for r in to_crawl
        if r["slug"] not in results
    ]

    if blocked and HAS_UNDETECTED:
        logger.info(f"Retrying {len(blocked)} blocked sites with UndetectedAdapter...")

        undetected_config = BrowserConfig(
            headless=True,
            verbose=False,
            enable_stealth=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            headers=browser_config.headers,
        )

        try:
            adapter = UndetectedAdapter()
            strategy = AsyncPlaywrightCrawlerStrategy(
                browser_config=undetected_config,
                browser_adapter=adapter,
            )
            async with AsyncWebCrawler(
                crawler_strategy=strategy, config=undetected_config
            ) as ua_crawler:
                for i, record in enumerate(blocked):
                    slug = record["slug"]
                    name = record["name"]
                    url = record["website"]

                    logger.info(
                        f"  [Undetected {i+1}/{len(blocked)}] {name} — {url}"
                    )

                    text = await crawl_fo_website_async(
                        ua_crawler, url, name, run_config
                    )

                    if text:
                        results[slug] = text
                        logger.info(
                            f"    UndetectedAdapter: {len(text):,} chars"
                        )
                    else:
                        logger.warning(
                            f"    UndetectedAdapter: still blocked — {name}"
                        )

                    if i < len(blocked) - 1:
                        await asyncio.sleep(2.0)

        except Exception as e:
            logger.warning(f"UndetectedAdapter session error: {e}")

        tier2_success = len(results) - tier1_success
        logger.info(
            f"Tier 2 (undetected) complete: {tier2_success}/{len(blocked)} "
            f"additional sites recovered"
        )
    elif blocked and not HAS_UNDETECTED:
        logger.info(
            f"{len(blocked)} sites blocked — upgrade crawl4ai for "
            f"UndetectedAdapter support"
        )

    success = len(results)
    logger.info(f"Crawl complete: {success}/{len(to_crawl)} sites returned content")
    return results


# ─── Sync wrappers for backward compatibility ───────────────────────

def crawl_fo_website(website_url: str, fo_name: str) -> Optional[str]:
    """Sync wrapper — crawls a single FO website."""
    if not website_url:
        return None

    logger.info(f"  Crawling: {website_url}")

    async def _crawl():
        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            enable_stealth=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=PAGE_TIMEOUT,
            wait_until="domcontentloaded",
            simulate_user=True,
            override_navigator=True,
            magic=True,
        )
        async with AsyncWebCrawler(config=browser_config) as crawler:
            return await crawl_fo_website_async(crawler, website_url, fo_name, run_config)

    try:
        text = asyncio.run(_crawl())
        if text:
            logger.info(f"    Got {len(text):,} chars from {fo_name}")
        else:
            logger.warning(f"    No content from {fo_name}")
        return text
    except Exception as e:
        logger.warning(f"    Error crawling {fo_name}: {e}")
        return None


def crawl_all_websites(
    records: list[dict],
    already_crawled: set[str] | None = None,
    delay: float = 1.0,
) -> dict[str, str]:
    """Sync wrapper for batch crawling."""
    return asyncio.run(crawl_all_websites_async(records, already_crawled))
