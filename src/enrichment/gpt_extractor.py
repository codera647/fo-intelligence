"""
Stage 3: GPT-Powered Extraction
=================================
Two-agent extraction from crawled website text using gpt-4o-mini:

  Agent A — Company Intelligence:
    description, investment_thesis, sectors, geographic_focus, founded_year

  Agent B — People & Contacts:
    team_members (name, title, email, linkedin),
    best_contacts (top 2-3 for outreach),
    primary_email, phone, address

Merges PipelineRoad data (Stage 1) with website-extracted data,
keeping PipelineRoad values where website data is missing.

Usage:
    from src.enrichment.gpt_extractor import extract_fo_intelligence
    enriched = extract_fo_intelligence(fo_record, crawled_text)
"""

import json
import logging
from typing import Optional

from openai import OpenAI
from config.settings import OPENAI_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

# ─── Prompts ────────────────────────────────────────────────────────

AGENT_A_SYSTEM = """You are a financial research analyst extracting company intelligence from a family office website.

Extract the following fields from the provided website text. If a field cannot be determined, use null.

Return ONLY valid JSON with this exact schema:
{
  "description": "2-3 sentence company description — what they do and who they serve",
  "investment_thesis": "Their core investment philosophy and approach (1-2 sentences)",
  "sectors": ["list", "of", "industry", "sectors", "they", "invest", "in"],
  "geographic_focus": ["list", "of", "regions", "or", "countries"],
  "founded_year": 2000,
  "firm_type": "Single Family Office | Multi Family Office | Hybrid | Unknown",
  "min_investment": "$X million (if mentioned, else null)",
  "notable_holdings": ["any", "notable", "portfolio", "companies", "or", "investments"],
  "aum": "$X billion or $X million — the total assets under management if mentioned anywhere on the site. null if not found",
  "aum_year": "The year this AUM figure refers to (e.g. 2025, 2024). Look for phrases like 'as of 2025', 'Q1 2025', 'December 2024'. null if not found",
  "recent_activity": {
    "title": "Headline or title of the most recent news/press/blog post",
    "date": "Date if visible (e.g. '2024-03-15' or 'March 2024'). null if not found",
    "url": "Direct URL to the article/post if visible in the page links. null if not found",
    "summary": "1-sentence summary of what happened (e.g. 'Announced $50M investment in XYZ Corp')"
  }
}

Be precise. Only extract what is explicitly stated or clearly implied. Do not hallucinate."""

AGENT_B_SYSTEM = """You are a research analyst extracting team and contact information from a family office website.

Extract ALL team members you can find with their details. Then identify the 2-3 BEST contacts for business outreach (prefer: Managing Director, Partner, CIO, Head of Investments, Principal — people who make investment decisions).

Return ONLY valid JSON with this exact schema:
{
  "team_members": [
    {
      "name": "Full Name",
      "title": "Their Title/Role",
      "email": "email@domain.com or null",
      "linkedin_url": "https://linkedin.com/in/... or null",
      "is_key_contact": true
    }
  ],
  "best_contacts": [
    {
      "name": "Full Name",
      "title": "Title",
      "reason": "Why this person is a good outreach target"
    }
  ],
  "primary_email": "best general contact email (info@, contact@, etc.) or null",
  "phone": "main phone number or null",
  "address": "office address or null"
}

Rules:
- Mark is_key_contact=true for decision makers (CEO, CIO, Partner, MD, Principal, Head of)
- For best_contacts, pick 2-3 people most likely to respond to an investment-related inquiry
- If no individual emails found, still capture the general contact email
- Do NOT invent people or contacts — only extract what's in the text"""


# ─── Core Extraction ─────────────────────────────────────────────────

def _call_gpt(system_prompt: str, user_content: str, label: str) -> Optional[dict]:
    """Call GPT and parse JSON response. Returns None on failure."""
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = json.loads(raw)
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"  {label}: JSON parse error: {e}")
        return None
    except Exception as e:
        logger.warning(f"  {label}: GPT call failed: {e}")
        return None


def extract_company_intelligence(crawled_text: str, fo_name: str) -> Optional[dict]:
    """Agent A: Extract company-level intelligence from crawled text."""
    user_msg = (
        f"Family Office: {fo_name}\n\n"
        f"Website content:\n{crawled_text[:6000]}"
    )
    return _call_gpt(AGENT_A_SYSTEM, user_msg, f"Agent A ({fo_name})")


def extract_people_contacts(crawled_text: str, fo_name: str) -> Optional[dict]:
    """Agent B: Extract team members and contact information."""
    user_msg = (
        f"Family Office: {fo_name}\n\n"
        f"Website content:\n{crawled_text[:6000]}"
    )
    return _call_gpt(AGENT_B_SYSTEM, user_msg, f"Agent B ({fo_name})")


# ─── Helpers ─────────────────────────────────────────────────────────

def _parse_year(value) -> Optional[int]:
    """Extract a 4-digit year from a string like '2024-12-31', '2025', 'Q1 2025', etc."""
    if not value:
        return None
    import re
    match = re.search(r'(20\d{2})', str(value))
    return int(match.group(1)) if match else None


# ─── Merge Logic ──────────────────────────────────────────────────────

def extract_fo_intelligence(fo_record: dict, crawled_text: str) -> dict:
    """Run both agents and merge results into the FO record.

    Args:
        fo_record: Original record from 01_discovered.json
        crawled_text: Raw text from website crawler (with structured markers)

    Returns:
        Enriched record with all extracted fields merged in.
    """
    enriched = dict(fo_record)  # shallow copy
    fo_name = fo_record.get("name", "Unknown")

    # ── Agent A: Company Intelligence ──
    company = extract_company_intelligence(crawled_text, fo_name)
    if company:
        # Only overwrite if we got better data
        if company.get("description") and len(company["description"]) > 20:
            enriched["website_description"] = company["description"]
        if company.get("investment_thesis"):
            enriched["website_investment_thesis"] = company["investment_thesis"]
        if company.get("sectors"):
            enriched["sectors"] = company["sectors"]
        if company.get("geographic_focus"):
            enriched["geographic_focus"] = company["geographic_focus"]
        if company.get("founded_year"):
            enriched["founded_year"] = company["founded_year"]
        if company.get("firm_type") and company["firm_type"] != "Unknown":
            enriched["firm_type"] = company["firm_type"]
        if company.get("min_investment"):
            enriched["min_investment"] = company["min_investment"]
        if company.get("notable_holdings"):
            enriched["notable_holdings"] = company["notable_holdings"]
        # AUM: keep the more recent value (website vs PipelineRoad)
        if company.get("aum"):
            website_year = _parse_year(company.get("aum_year"))
            pipeline_year = _parse_year(enriched.get("aum_date"))
            if website_year and pipeline_year:
                if website_year >= pipeline_year:
                    enriched["aum"] = company["aum"]
                    enriched["aum_date"] = str(website_year)
                    enriched["aum_source"] = "website"
                # else: keep PipelineRoad value (it's newer or same)
            elif website_year:
                # PipelineRoad has no date — website wins if it has a year
                enriched["aum"] = company["aum"]
                enriched["aum_date"] = str(website_year)
                enriched["aum_source"] = "website"
            elif not enriched.get("aum"):
                # No AUM at all — take whatever we found
                enriched["aum"] = company["aum"]
                enriched["aum_source"] = "website"
        if company.get("recent_activity"):
            enriched["recent_activity"] = company["recent_activity"]

        logger.info(f"    Agent A: ✓ {len([v for v in company.values() if v])} fields extracted")
    else:
        logger.warning(f"    Agent A: ✗ No data")

    # ── Agent B: People & Contacts ──
    people = extract_people_contacts(crawled_text, fo_name)
    if people:
        if people.get("team_members"):
            enriched["team_members"] = people["team_members"]
            enriched["team_size"] = len(people["team_members"])
        if people.get("best_contacts"):
            enriched["best_contacts"] = people["best_contacts"]
        if people.get("primary_email"):
            enriched["primary_email"] = people["primary_email"]
        if people.get("phone"):
            enriched["phone"] = people["phone"]
        if people.get("address"):
            enriched["address"] = people["address"]

        team_count = len(people.get("team_members", []))
        contact_count = len(people.get("best_contacts", []))
        logger.info(f"    Agent B: ✓ {team_count} team members, {contact_count} key contacts")
    else:
        logger.warning(f"    Agent B: ✗ No data")

    # ── Also parse structured markers from crawled text ──
    _merge_structured_markers(enriched, crawled_text)

    return enriched


def _merge_structured_markers(enriched: dict, crawled_text: str):
    """Extract data from the website_crawler's structured markers.

    The BFS crawler embeds markers like:
      === EXTRACTED_EMAILS ===
      === CORPORATE_LINKEDIN ===
      === LINKEDIN_PROFILES ===
      === TEAM_MEMBERS ===
    """
    # Corporate LinkedIn (only if not already set)
    if not enriched.get("corporate_linkedin"):
        marker = "=== CORPORATE_LINKEDIN ==="
        if marker in crawled_text:
            idx = crawled_text.index(marker) + len(marker)
            end = crawled_text.find("\n\n", idx)
            if end == -1:
                end = len(crawled_text)
            url = crawled_text[idx:end].strip()
            if url.startswith("http"):
                enriched["corporate_linkedin"] = url

    # Extracted emails (supplement, don't overwrite)
    if not enriched.get("extracted_emails"):
        marker = "=== EXTRACTED_EMAILS ==="
        if marker in crawled_text:
            idx = crawled_text.index(marker) + len(marker)
            end = crawled_text.find("\n\n", idx)
            if end == -1:
                end = len(crawled_text)
            emails = [e.strip() for e in crawled_text[idx:end].strip().split("\n") if "@" in e]
            if emails:
                enriched["extracted_emails"] = emails

    # Corporate email (only if not set by GPT)
    if not enriched.get("primary_email"):
        marker = "=== CORPORATE_EMAIL ==="
        if marker in crawled_text:
            idx = crawled_text.index(marker) + len(marker)
            end = crawled_text.find("\n\n", idx)
            if end == -1:
                end = len(crawled_text)
            email = crawled_text[idx:end].strip()
            if "@" in email:
                enriched["primary_email"] = email

    # LinkedIn profiles
    marker = "=== LINKEDIN_PROFILES ==="
    if marker in crawled_text:
        idx = crawled_text.index(marker) + len(marker)
        end = crawled_text.find("\n\n", idx)
        if end == -1:
            end = len(crawled_text)
        urls = [u.strip() for u in crawled_text[idx:end].strip().split("\n")
                if "linkedin.com/in/" in u]
        if urls and not enriched.get("linkedin_profiles"):
            enriched["linkedin_profiles"] = urls

    # Social links
    marker = "=== OTHER_SOCIALS ==="
    if marker in crawled_text:
        idx = crawled_text.index(marker) + len(marker)
        end = crawled_text.find("\n\n", idx)
        if end == -1:
            end = len(crawled_text)
        urls = [u.strip() for u in crawled_text[idx:end].strip().split("\n") if u.strip()]
        if urls:
            enriched["social_links"] = urls
