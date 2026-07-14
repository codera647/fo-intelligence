"""Website scraper — BFS crawl with structured extraction.

Crawls up to 20 pages per site using BFS link-following (depth=3).
Extracts structured data directly from HTML:
  - Emails from mailto: links and text patterns
  - Social links (LinkedIn, Twitter/X) from <a> tags
  - Contact names/titles from team pages
  - Phone numbers from tel: links
"""

import re
import time
import logging
import warnings
import requests
import urllib3
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Set, Tuple
from urllib.parse import urljoin, urlparse
from collections import deque

# Suppress SSL warnings for fallback requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Pages most likely to contain rich FO data — prioritized in BFS
HIGH_PRIORITY_PATHS = {
    "about", "about-us", "team", "our-team", "leadership", "people",
    "principals", "contact", "contact-us", "connect", "investments",
    "portfolio", "strategy", "what-we-do", "philosophy", "approach",
    "focus", "partners", "management", "staff", "advisory", "board",
}

# Max pages and depth
MAX_PAGES = 20
MAX_DEPTH = 3
PAGE_TIMEOUT = 12

# Email regex
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)

# Junk email patterns to exclude
JUNK_EMAIL_PATTERNS = {
    "example.com", "sentry.io", "wixpress.com", "wordpress.com",
    "squarespace.com", "gravatar.com", "w3.org", "schema.org",
    "googleapis.com", "jquery.com", "google.com", "facebook.com",
    "twitter.com", "linkedin.com", "cloudflare.com", "amazonaws.com",
}


class SiteData:
    """Accumulated structured data from crawling a site."""

    def __init__(self):
        self.pages_text: List[str] = []
        self.emails: Set[str] = set()
        self.linkedin_urls: Set[str] = set()
        self.twitter_urls: Set[str] = set()
        self.facebook_urls: Set[str] = set()
        self.instagram_urls: Set[str] = set()
        self.youtube_urls: Set[str] = set()
        self.team_members: List[Dict] = []
        self.corporate_linkedin: Optional[str] = None


def scrape_website(url: str, timeout: int = PAGE_TIMEOUT) -> Optional[str]:
    """BFS crawl a website and return combined text + structured extraction.

    Returns combined text content from all crawled pages.
    Structured data (emails, LinkedIn, team members) is stored as
    metadata markers within the text for downstream extraction.
    """
    if not url:
        return None
    if not url.startswith("http"):
        url = "https://" + url

    site_data = SiteData()
    crawled = _bfs_crawl(url, site_data, timeout)

    if not crawled:
        return None

    # Build combined text with structured data markers
    sections = []
    for page_label, page_text in site_data.pages_text:
        sections.append(f"=== {page_label} ===\n{page_text}")

    # Append structured extraction results as parseable markers
    if site_data.emails:
        valid_emails = [e for e in site_data.emails if _is_valid_email(e)]
        if valid_emails:
            sections.append(f"=== EXTRACTED_EMAILS ===\n" + "\n".join(valid_emails))
            # Pick best corporate email (info@, contact@, office@, general@, hello@)
            corporate_prefixes = ["info@", "contact@", "office@", "general@", "hello@", "enquiries@", "inquiries@"]
            corp_email = None
            for prefix in corporate_prefixes:
                for e in valid_emails:
                    if e.lower().startswith(prefix):
                        corp_email = e
                        break
                if corp_email:
                    break
            if corp_email:
                sections.append(f"=== CORPORATE_EMAIL ===\n{corp_email}")

    if site_data.corporate_linkedin:
        sections.append(f"=== CORPORATE_LINKEDIN ===\n{site_data.corporate_linkedin}")

    if site_data.linkedin_urls:
        sections.append(f"=== LINKEDIN_PROFILES ===\n" + "\n".join(site_data.linkedin_urls))

    # Other social links (Twitter, Facebook, Instagram, YouTube)
    other_socials = []
    for url in site_data.twitter_urls:
        other_socials.append(url)
    for url in site_data.facebook_urls:
        other_socials.append(url)
    for url in site_data.instagram_urls:
        other_socials.append(url)
    for url in site_data.youtube_urls:
        other_socials.append(url)
    if other_socials:
        sections.append(f"=== OTHER_SOCIALS ===\n" + "\n".join(other_socials))

    if site_data.team_members:
        members_text = []
        for m in site_data.team_members[:10]:  # Top 10
            parts = [m.get("name", "")]
            if m.get("title"):
                parts.append(m["title"])
            if m.get("email"):
                parts.append(m["email"])
            if m.get("linkedin"):
                parts.append(m["linkedin"])
            members_text.append(" | ".join(parts))
        sections.append(f"=== TEAM_MEMBERS ===\n" + "\n".join(members_text))

    combined = "\n\n".join(sections)

    # Truncate to 8000 chars for LLM context
    if len(combined) > 8000:
        combined = combined[:8000] + "\n... [truncated]"

    return combined if len(combined) > 50 else None


def scrape_single_page(url: str, timeout: int = PAGE_TIMEOUT) -> Optional[str]:
    """Scrape just one page — used for targeted page scraping."""
    text, _, _ = _fetch_page(url, timeout)
    return text


def _bfs_crawl(start_url: str, site_data: SiteData, timeout: int) -> bool:
    """BFS crawl from start_url, collecting text and structured data."""
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc
    base = f"{parsed_start.scheme}://{parsed_start.netloc}"

    visited: Set[str] = set()
    # Queue entries: (url, depth, priority_label)
    queue: deque = deque()
    queue.append((start_url, 0, "HOMEPAGE"))

    pages_crawled = 0

    while queue and pages_crawled < MAX_PAGES:
        url, depth, label = queue.popleft()

        # Normalize URL for dedup
        norm_url = url.split("?")[0].split("#")[0].rstrip("/")
        if norm_url in visited:
            continue
        visited.add(norm_url)

        # Fetch page
        text, soup, links = _fetch_page(url, timeout)
        if not text:
            continue

        pages_crawled += 1
        site_data.pages_text.append((label, text))

        # Extract structured data from this page
        if soup:
            _extract_emails_from_soup(soup, text, site_data)
            _extract_social_links(soup, url, site_data)

            # If this looks like a team page, extract team members
            if _is_team_page(label, url, text):
                _extract_team_members(soup, site_data)

        # Add discovered links to queue (BFS)
        if depth < MAX_DEPTH and links:
            # Prioritize high-value pages
            prioritized = []
            regular = []

            for link_url in links:
                link_parsed = urlparse(link_url)
                # Same domain only
                if link_parsed.netloc != base_domain:
                    continue
                # Skip non-HTML
                path = link_parsed.path.lower()
                if any(path.endswith(ext) for ext in [".pdf", ".jpg", ".png", ".gif", ".css", ".js", ".xml", ".zip"]):
                    continue

                link_norm = link_url.split("?")[0].split("#")[0].rstrip("/")
                if link_norm in visited:
                    continue

                # Check if high priority
                path_parts = set(path.strip("/").split("/"))
                if path_parts & HIGH_PRIORITY_PATHS:
                    page_label = path.strip("/").replace("/", "_").upper() or "SUBPAGE"
                    prioritized.append((link_url, depth + 1, page_label))
                else:
                    page_label = path.strip("/").replace("/", "_").upper() or "SUBPAGE"
                    regular.append((link_url, depth + 1, page_label))

            # Add prioritized first, then regular
            for item in prioritized:
                queue.appendleft(item)  # Front of queue
            for item in regular:
                queue.append(item)  # Back of queue

        time.sleep(0.2)

    logger.info(f"BFS crawled {pages_crawled} pages from {start_url}")
    return pages_crawled > 0


def _fetch_page(url: str, timeout: int = PAGE_TIMEOUT):
    """Fetch a single page with robust error handling.

    Returns (text, soup, outbound_links).

    Handles:
    - SSL certificate errors (retry without verification)
    - Encoding detection (chardet / apparent_encoding fallback)
    - Relaxed content-type checking (accept empty Content-Type)
    - 403 retry with alternate User-Agent
    """
    for attempt in range(2):
        try:
            # On second attempt: disable SSL verify + alternate UA
            verify_ssl = attempt == 0
            headers = HEADERS if attempt == 0 else {
                **HEADERS,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            }

            resp = requests.get(
                url, headers=headers, timeout=timeout,
                allow_redirects=True, verify=verify_ssl,
            )

            # Retry on 403 with alternate UA (first attempt only)
            if resp.status_code == 403 and attempt == 0:
                logger.debug(f"403 on first attempt, retrying with alternate UA: {url}")
                continue

            if resp.status_code not in (200, 206):
                return None, None, []

            content_type = resp.headers.get("Content-Type", "")
            # Accept empty content-type (some servers omit it) or any text/html variant
            if content_type and "text/" not in content_type and "html" not in content_type and "xhtml" not in content_type:
                return None, None, []

            # Fix encoding — requests sometimes guesses wrong
            if resp.encoding and resp.encoding.lower() in ("iso-8859-1", "latin-1"):
                if resp.apparent_encoding:
                    resp.encoding = resp.apparent_encoding

            html = resp.text

            soup = BeautifulSoup(html, "html.parser")

            # Extract outbound links before removing elements
            links = []
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = urljoin(url, href)
                if full_url.startswith("http"):
                    links.append(full_url)

            # Remove non-content elements for text extraction
            for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                             "iframe", "noscript", "svg", "form"]):
                tag.decompose()

            # Get text
            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip() and len(line.strip()) > 3]
            clean_text = "\n".join(lines)

            # Re-parse full HTML for structured extraction (before decompose)
            full_soup = BeautifulSoup(html, "html.parser")

            return clean_text if len(clean_text) > 30 else None, full_soup, links

        except requests.exceptions.SSLError:
            if attempt == 0:
                logger.debug(f"SSL error, retrying without verification: {url}")
                continue
            logger.debug(f"SSL error (both attempts): {url}")
            return None, None, []
        except requests.exceptions.Timeout:
            logger.debug(f"Timeout: {url}")
            return None, None, []
        except requests.exceptions.ConnectionError:
            logger.debug(f"Connection error: {url}")
            return None, None, []
        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            return None, None, []

    return None, None, []


def _extract_emails_from_soup(soup: BeautifulSoup, text: str, site_data: SiteData):
    """Extract emails from mailto: links and text content."""
    # From mailto: links
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0].strip()
            if _is_valid_email(email):
                site_data.emails.add(email)

    # From text patterns
    for match in EMAIL_PATTERN.finditer(text):
        email = match.group()
        if _is_valid_email(email):
            site_data.emails.add(email)


def _extract_social_links(soup: BeautifulSoup, page_url: str, site_data: SiteData):
    """Extract LinkedIn, Twitter, Facebook, Instagram, YouTube URLs from page links."""
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        href_lower = href.lower()

        # Corporate LinkedIn (company page)
        if "linkedin.com/company/" in href_lower and not site_data.corporate_linkedin:
            clean = href.split("?")[0].rstrip("/") + "/"
            site_data.corporate_linkedin = clean

        # Individual LinkedIn profiles
        elif "linkedin.com/in/" in href_lower:
            clean = href.split("?")[0].rstrip("/") + "/"
            site_data.linkedin_urls.add(clean)

        # Twitter/X
        elif "twitter.com/" in href_lower or "x.com/" in href_lower:
            if not any(skip in href_lower for skip in ["/intent/", "/share", "/status/"]):
                site_data.twitter_urls.add(href.split("?")[0])

        # Facebook
        elif "facebook.com/" in href_lower:
            if not any(skip in href_lower for skip in ["/sharer", "/share.", "/dialog/", "/plugins/"]):
                site_data.facebook_urls.add(href.split("?")[0])

        # Instagram
        elif "instagram.com/" in href_lower:
            if not any(skip in href_lower for skip in ["/embed", "/p/", "/reel/"]):
                site_data.instagram_urls.add(href.split("?")[0])

        # YouTube (channel/user pages only)
        elif "youtube.com/" in href_lower:
            if any(yt in href_lower for yt in ["/channel/", "/c/", "/user/", "/@"]):
                site_data.youtube_urls.add(href.split("?")[0])


def _is_team_page(label: str, url: str, text: str) -> bool:
    """Detect if a page is a team/leadership page."""
    label_lower = label.lower()
    url_lower = url.lower()

    team_keywords = {"team", "leadership", "people", "principals", "partners",
                     "management", "staff", "advisory", "board", "our-team"}

    # Check URL path
    path = urlparse(url_lower).path.strip("/")
    path_parts = set(path.split("/"))
    if path_parts & team_keywords:
        return True

    # Check label
    if any(kw in label_lower for kw in team_keywords):
        return True

    # Check text content — many name+title patterns suggest team page
    title_patterns = r'(?:CEO|CIO|CFO|COO|President|Managing Director|Partner|Founder|Principal|Chairman|Director)'
    matches = re.findall(title_patterns, text, re.IGNORECASE)
    if len(matches) >= 3:
        return True

    return False


def _extract_team_members(soup: BeautifulSoup, site_data: SiteData):
    """Extract team members (name + title) from a team page.

    Looks for common patterns:
    - Cards/divs with h2/h3 for name and p/span for title
    - Definition lists
    - Structured containers with class names like 'team-member', 'bio', etc.
    """
    members = []

    # Strategy 1: Look for team member containers
    team_selectors = [
        {"class_": re.compile(r'team|member|bio|person|staff|leader|principal', re.I)},
    ]

    for selector in team_selectors:
        containers = soup.find_all(["div", "article", "li", "section"], **selector)
        for container in containers:
            member = _parse_team_container(container)
            if member and member.get("name"):
                members.append(member)

    # Strategy 2: If no containers found, look for heading+paragraph pairs
    if not members:
        for heading in soup.find_all(["h2", "h3", "h4"]):
            name = heading.get_text(strip=True)
            if not name or len(name) > 60 or len(name) < 3:
                continue

            # Check if next sibling has a title-like text
            next_el = heading.find_next_sibling(["p", "span", "div"])
            if next_el:
                title = next_el.get_text(strip=True)
                title_pattern = r'(?:CEO|CIO|CFO|COO|President|Director|Partner|Founder|Managing|Principal|VP|Vice|Head|Officer|Chairman|Analyst|Advisor)'
                if re.search(title_pattern, title, re.IGNORECASE) and len(title) < 80:
                    members.append({"name": name, "title": title})

    # Deduplicate
    seen = set()
    for m in members:
        key = m.get("name", "").lower()
        if key and key not in seen:
            seen.add(key)
            site_data.team_members.append(m)


def _parse_team_container(container) -> Optional[Dict]:
    """Parse a single team member container for name, title, email, LinkedIn."""
    member = {}

    # Name — usually in a heading
    for tag in ["h2", "h3", "h4", "h5", "strong"]:
        el = container.find(tag)
        if el:
            name = el.get_text(strip=True)
            if 3 <= len(name) <= 60 and not any(c.isdigit() for c in name):
                member["name"] = name
                break

    if not member.get("name"):
        # Try class-based name detection
        name_el = container.find(class_=re.compile(r'name|title', re.I))
        if name_el:
            name = name_el.get_text(strip=True)
            if 3 <= len(name) <= 60:
                member["name"] = name

    # Title — usually in a paragraph or span after the name
    for tag in ["p", "span", "div"]:
        els = container.find_all(tag)
        for el in els:
            text = el.get_text(strip=True)
            title_pattern = r'(?:CEO|CIO|CFO|COO|President|Director|Partner|Founder|Managing|Principal|VP|Vice|Head|Officer|Chairman|Analyst|Advisor|Manager)'
            if re.search(title_pattern, text, re.IGNORECASE) and len(text) < 80:
                member["title"] = text
                break
        if member.get("title"):
            break

    # Email — from mailto: link within container
    for a_tag in container.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0].strip()
            if _is_valid_email(email):
                member["email"] = email
                break

    # LinkedIn — from link within container
    for a_tag in container.find_all("a", href=True):
        href = a_tag["href"]
        if "linkedin.com/in/" in href.lower():
            member["linkedin"] = href.split("?")[0]
            break

    return member if member.get("name") else None


def _is_valid_email(email: str) -> bool:
    """Validate email format and exclude junk domains."""
    if not email or "@" not in email:
        return False

    # Basic format check
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return False

    # Exclude junk domains
    domain = email.split("@")[1].lower()
    if any(junk in domain for junk in JUNK_EMAIL_PATTERNS):
        return False

    # Exclude common image/asset filenames that look like emails
    local_part = email.split("@")[0].lower()
    if any(ext in local_part for ext in [".png", ".jpg", ".gif", ".svg"]):
        return False

    return True


def check_url_status(url: str) -> str:
    """Check URL quality — returns Highest/Medium/Medium-Low/Lower/Not Found."""
    if not url:
        return "Not Found"

    if not url.startswith("http"):
        url = "https://" + url

    for verify_ssl in (True, False):
        try:
            resp = requests.head(
                url, headers=HEADERS, timeout=10,
                allow_redirects=True, verify=verify_ssl,
            )

            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type or not content_type:
                    return "Highest"
                return "Medium"
            elif resp.status_code in (301, 302, 308):
                return "Medium"
            elif resp.status_code == 403:
                # Some sites block HEAD but allow GET
                try:
                    resp2 = requests.get(
                        url, headers=HEADERS, timeout=10,
                        allow_redirects=True, verify=verify_ssl,
                        stream=True,
                    )
                    resp2.close()
                    if resp2.status_code == 200:
                        return "Medium"
                except Exception:
                    pass
                return "Medium-Low"
            elif resp.status_code == 405:
                # HEAD not allowed — try GET
                try:
                    resp2 = requests.get(
                        url, headers=HEADERS, timeout=10,
                        allow_redirects=True, verify=verify_ssl,
                        stream=True,
                    )
                    resp2.close()
                    if resp2.status_code == 200:
                        return "Highest"
                except Exception:
                    pass
                return "Medium"
            else:
                return "Lower"

        except requests.exceptions.SSLError:
            if verify_ssl:
                continue  # retry without SSL verification
            return "Lower"
        except requests.exceptions.Timeout:
            return "Lower"
        except requests.exceptions.ConnectionError:
            return "Not Found"
        except Exception:
            return "Lower"

    return "Lower"
