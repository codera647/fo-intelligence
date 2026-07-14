"""LLM-based extraction — sends scraped content to OpenAI for structured data extraction."""

import json
import logging
from typing import Dict, Optional
from openai import OpenAI

from config.settings import OPENAI_API_KEY, LLM_MODEL
from config.prompts import WEBSITE_EXTRACTION_PROMPT, NEWS_EXTRACTION_PROMPT, LLM_ENRICHMENT_PROMPT

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences and clean LLM JSON output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (code fences)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Remove any trailing commas before } (common LLM mistake)
    text = text.replace(",\n}", "\n}").replace(",}", "}")
    return text


def extract_from_website(url: str, content: str) -> Dict:
    """Use LLM to extract structured FO data from website content."""
    if not content or len(content) < 30:
        return {}

    prompt = WEBSITE_EXTRACTION_PROMPT.format(url=url, content=content[:4000])

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise data extraction assistant specializing in Family Office intelligence. Extract ALL available data points. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
        )

        text = _clean_json_response(response.choices[0].message.content)
        data = json.loads(text)

        # Remove null values and metadata keys
        clean = {k: v for k, v in data.items() if v is not None and v != "" and v != "null" and not k.startswith("_")}
        logger.info(f"Extracted {len(clean)} fields from {url}")
        return clean

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error for {url}: {e}")
        return {}
    except Exception as e:
        logger.warning(f"LLM extraction failed for {url}: {e}")
        return {}


def extract_from_news(source: str, content: str) -> Dict:
    """Use LLM to extract FO intelligence from news content."""
    if not content:
        return {}

    prompt = NEWS_EXTRACTION_PROMPT.format(source=source, content=content[:2000])

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise data extraction assistant. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
        )

        text = _clean_json_response(response.choices[0].message.content)
        return json.loads(text)

    except Exception as e:
        logger.warning(f"News extraction failed: {e}")
        return {}


def enrich_with_llm(name: str, existing_data: Dict) -> Dict:
    """Use LLM training knowledge to fill gaps — aggressive for known entities.

    For well-known family offices, the LLM has extensive knowledge about
    their headquarters, key personnel, investment focus, founding history, etc.
    This function aggressively leverages that knowledge.
    """
    from config.schema import COLUMN_ORDER

    # Build existing data summary (non-empty fields)
    filled_fields = {}
    for k, v in existing_data.items():
        if v and k in COLUMN_ORDER and str(v).strip() and str(v).lower() not in ("none", "null", "n/a", "unknown", "not found"):
            filled_fields[k] = v

    # Build missing fields list
    skip_fields = {"data_completeness_score", "confidence_score", "primary_sources"}
    empty_fields = [k for k in COLUMN_ORDER if k not in filled_fields and k not in skip_fields]

    if not empty_fields:
        return {}

    # Format existing data for the prompt
    existing_str = json.dumps(filled_fields, indent=2) if filled_fields else "{}"
    missing_str = ", ".join(empty_fields)

    prompt = LLM_ENRICHMENT_PROMPT.format(
        name=name,
        existing_data=existing_str,
        missing_fields=missing_str,
    )

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert Family Office research analyst. You have deep knowledge of "
                        "the wealth management industry including major family offices worldwide, their "
                        "principals, investment strategies, and headquarters. Provide accurate, detailed "
                        "information from your knowledge. Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        text = _clean_json_response(response.choices[0].message.content)
        data = json.loads(text)

        # Clean: remove nulls, metadata keys, and fields not in schema
        clean_data = {}
        for k, v in data.items():
            if (
                v is not None
                and v != ""
                and str(v).lower() not in ("null", "n/a", "none", "unknown")
                and not k.startswith("_")
                and k in COLUMN_ORDER
            ):
                clean_data[k] = v

        logger.info(f"LLM enriched {len(clean_data)} fields for {name}")
        return clean_data

    except json.JSONDecodeError as e:
        logger.warning(f"LLM enrichment JSON error for {name}: {e}")
        return {}
    except Exception as e:
        logger.warning(f"LLM enrichment failed for {name}: {e}")
        return {}
