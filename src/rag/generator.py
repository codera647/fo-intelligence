"""RAG generator — takes retrieved records + query → natural language answer."""

import logging
from typing import List, Dict
from openai import OpenAI

from config.settings import OPENAI_API_KEY, LLM_MODEL, TOP_K
from config.prompts import RAG_SYSTEM_PROMPT, RAG_QUERY_PROMPT
from .retriever import search_family_offices

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)


def query_rag(
    question: str,
    top_k: int = TOP_K,
    filters: Dict | None = None,
) -> Dict:
    """Full RAG pipeline: embed query → retrieve → generate answer.

    Returns:
        {
            "answer": str,
            "records": List[Dict],  # retrieved records
            "query": str,
        }
    """
    # ── Retrieve ───────────────────────────────────────────────────
    records = search_family_offices(query=question, top_k=top_k, filters=filters)

    if not records:
        return {
            "answer": "No matching Family Office records found for your query. Try broadening your search terms.",
            "records": [],
            "query": question,
        }

    # ── Build context from retrieved records ───────────────────────
    context = _format_records_for_context(records)

    # ── Generate answer ────────────────────────────────────────────
    answer = _generate_answer(question, context, len(records))

    return {
        "answer": answer,
        "records": records,
        "query": question,
    }


def _format_records_for_context(records: List[Dict]) -> str:
    """Format retrieved records into context string for the LLM."""
    parts = []

    for i, record in enumerate(records, 1):
        lines = [f"--- Record {i} (Similarity: {record.get('_similarity_score', 'N/A')}) ---"]
        lines.append(f"Name: {record.get('family_office_name', 'Unknown')}")

        if record.get("entity_type"):
            lines.append(f"Type: {record['entity_type']}")
        if record.get("aum_estimated"):
            lines.append(f"AUM: {record['aum_estimated']}")
        if record.get("investment_thesis"):
            lines.append(f"Investment Thesis: {record['investment_thesis']}")
        if record.get("investing_sectors"):
            lines.append(f"Sectors: {record['investing_sectors']}")

        location_parts = [p for p in [record.get("hq_city"), record.get("hq_state"), record.get("hq_country")] if p]
        if location_parts:
            lines.append(f"Location: {', '.join(location_parts)}")

        if record.get("contact_name"):
            contact = record["contact_name"]
            if record.get("contact_title"):
                contact += f" ({record['contact_title']})"
            lines.append(f"Contact: {contact}")

        if record.get("contact_email"):
            lines.append(f"Email: {record['contact_email']}")
        if record.get("recent_activity"):
            lines.append(f"Recent Activity: {record['recent_activity']}")
        if record.get("key_investments"):
            lines.append(f"Key Investments: {record['key_investments']}")
        if record.get("website_url"):
            lines.append(f"Website: {record['website_url']}")

        lines.append(f"Confidence: {record.get('confidence_score', 'N/A')}%")
        lines.append(f"Completeness: {record.get('data_completeness_score', 'N/A')}%")

        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _generate_answer(question: str, context: str, total_records: int) -> str:
    """Use LLM to generate a natural language answer from context."""
    system_msg = RAG_SYSTEM_PROMPT.format(total_records=total_records)
    user_msg = RAG_QUERY_PROMPT.format(context=context, question=question)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"RAG generation failed: {e}")
        return f"Error generating answer: {str(e)}. Retrieved {total_records} matching records."
