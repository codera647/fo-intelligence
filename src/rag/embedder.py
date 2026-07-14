"""Embedding module — converts FO records to vectors for Qdrant."""

import logging
from typing import List, Dict
from openai import OpenAI

from config.settings import OPENAI_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)


def create_embedding(text: str) -> List[float]:
    """Create a single embedding vector from text."""
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return [0.0] * EMBEDDING_DIM


def create_embeddings_batch(texts: List[str], batch_size: int = 20) -> List[List[float]]:
    """Create embeddings for multiple texts in batches."""
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
        except Exception as e:
            logger.error(f"Batch embedding failed at index {i}: {e}")
            # Fill with zero vectors for failed batch
            all_embeddings.extend([[0.0] * EMBEDDING_DIM] * len(batch))

    return all_embeddings


def record_to_text(record: Dict) -> str:
    """Convert a FO record dict into a natural-language text for embedding.

    This is the 'document' that gets embedded and stored in Qdrant.
    Includes all relevant fields to enable semantic search.
    """
    parts = []

    name = record.get("family_office_name", "Unknown")
    parts.append(f"Family Office: {name}")

    if record.get("entity_type"):
        parts.append(f"Type: {record['entity_type']}")

    if record.get("description"):
        parts.append(f"Description: {record['description']}")

    if record.get("aum_estimated"):
        parts.append(f"AUM: {record['aum_estimated']}")

    if record.get("investment_thesis"):
        parts.append(f"Investment Thesis: {record['investment_thesis']}")

    if record.get("investing_sectors"):
        parts.append(f"Investing Sectors: {record['investing_sectors']}")

    if record.get("hq_city") or record.get("hq_state") or record.get("hq_country"):
        location_parts = [p for p in [record.get("hq_city"), record.get("hq_state"), record.get("hq_country")] if p]
        parts.append(f"Location: {', '.join(location_parts)}")

    if record.get("contact_name"):
        contact = record["contact_name"]
        if record.get("contact_title"):
            contact += f" ({record['contact_title']})"
        parts.append(f"Key Contact: {contact}")

    if record.get("recent_activity"):
        parts.append(f"Recent Activity: {record['recent_activity']}")

    if record.get("key_investments"):
        parts.append(f"Key Investments: {record['key_investments']}")

    if record.get("year_founded"):
        parts.append(f"Founded: {record['year_founded']}")

    return "\n".join(parts)
