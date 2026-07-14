"""Family Office classifier — uses OpenRouter (Claude 3.5 Haiku) to verify
whether a candidate entity is actually a family office.

Called after website scraping so we can pass real website content for
accurate classification instead of relying on name alone.
"""

import json
import logging
import requests
from typing import Dict, Optional

from config.settings import OPENROUTER_API_KEY, OPENROUTER_MODEL

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

CLASSIFICATION_PROMPT = """You are an expert financial analyst specializing in family offices.
Analyze the following entity and determine if it is a family office (Single Family Office or Multi Family Office).

Entity Name: {name}
{website_section}
{notes_section}

A family office is a private wealth management firm that manages investments for a single wealthy family (SFO) or multiple wealthy families (MFO).

These are NOT family offices — reject them:
- Hedge funds, PE firms, VC firms (even if founded by one person)
- Sovereign wealth funds (government-owned like Temasek, Mubadala, GIC, ADIA)
- Registered Investment Advisors (RIAs) serving the general public
- Mutual fund companies, ETF providers
- Banks, insurance companies, credit unions
- Charitable foundations only (unless they also run a family investment office)
- General wealth management / financial advisory firms serving retail or institutional clients
- Investment management companies open to outside investors

Respond in EXACTLY this JSON format and nothing else:
{{"is_family_office": true, "entity_type": "Single Family Office", "confidence": 0.9, "reasoning": "one sentence"}}"""


def classify_entity(
    name: str,
    website_content: str = None,
    notes: str = None,
) -> Dict:
    """Classify whether an entity is a family office using LLM.

    Args:
        name: Entity name
        website_content: Scraped website text (about page, homepage, etc.)
        notes: Discovery notes/description

    Returns:
        Dict with keys: is_family_office, entity_type, confidence, reasoning
    """
    default_pass = {
        "is_family_office": True,
        "entity_type": None,
        "confidence": 0.5,
        "reasoning": "Classification skipped",
    }

    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set — skipping FO classification")
        return default_pass

    # Build context sections
    website_section = ""
    if website_content:
        summary = _extract_summary(website_content)
        if summary:
            website_section = f"Website Content:\n{summary}"

    notes_section = ""
    if notes:
        notes_section = f"Additional Context: {notes}"

    prompt = CLASSIFICATION_PROMPT.format(
        name=name,
        website_section=website_section,
        notes_section=notes_section,
    )

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fo-intelligence.com",
            "X-Title": "FO Intelligence Pipeline",
        }

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 200,
        }

        resp = requests.post(
            OPENROUTER_URL, headers=headers, json=payload, timeout=30
        )

        if resp.status_code != 200:
            logger.warning(f"OpenRouter returned {resp.status_code}: {resp.text[:200]}")
            return default_pass

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(content)

        is_fo = result.get("is_family_office", True)
        entity_type = result.get("entity_type", "Unknown")
        confidence = result.get("confidence", 0.5)
        reasoning = result.get("reasoning", "")

        status = "FO" if is_fo else "NOT FO"
        logger.info(
            f"FO Classification: {name} -> {status} "
            f"({entity_type}, {confidence:.0%}) — {reasoning}"
        )

        return {
            "is_family_office": is_fo,
            "entity_type": entity_type if is_fo else "Not a Family Office",
            "confidence": confidence,
            "reasoning": reasoning,
        }

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse classifier response for '{name}': {e}")
        return default_pass
    except Exception as e:
        logger.warning(f"FO classification failed for '{name}': {e}")
        return default_pass


def _extract_summary(content: str, max_chars: int = 2000) -> str:
    """Extract a meaningful summary from scraped website content.

    Prioritizes About/Overview sections, falls back to first meaningful text.
    """
    if not content:
        return ""

    # Try to find About section first
    content_upper = content.upper()
    about_markers = [
        "=== ABOUT", "=== WHO WE ARE", "=== OVERVIEW",
        "=== OUR FIRM", "=== OUR STORY", "=== OUR MISSION",
    ]
    for marker in about_markers:
        if marker in content_upper:
            idx = content_upper.index(marker)
            section = content[idx:]
            end = section.find("\n===", len(marker))
            if end > 0:
                section = section[:end]
            return section[:max_chars].strip()

    # Fall back: collect lines with real content (skip nav/headers)
    lines = content.split("\n")
    meaningful = []
    total_chars = 0
    for line in lines:
        line = line.strip()
        if len(line) > 30 and not line.startswith("==="):
            meaningful.append(line)
            total_chars += len(line)
            if total_chars >= max_chars:
                break

    return "\n".join(meaningful)[:max_chars]
