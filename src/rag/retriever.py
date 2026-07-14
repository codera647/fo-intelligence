"""Retriever — semantic search + structured filtering over Qdrant."""

import logging
from typing import List, Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

from config.settings import COLLECTION_NAME, TOP_K
from .embedder import create_embedding
from .indexer import get_qdrant_client

logger = logging.getLogger(__name__)


def search_family_offices(
    query: str,
    top_k: int = TOP_K,
    filters: Optional[Dict] = None,
    client: QdrantClient | None = None,
) -> List[Dict]:
    """Semantic search over FO records with optional structured filters.

    Args:
        query: Natural language query (gets embedded for vector search)
        top_k: Number of results to return
        filters: Optional structured filters, e.g.:
            {"entity_type": "Single Family Office", "hq_country": "USA"}

    Returns:
        List of matching records with similarity scores
    """
    if client is None:
        client = get_qdrant_client()

    # Create query embedding
    query_vector = create_embedding(query)

    # Build Qdrant filter from structured filters
    qdrant_filter = _build_filter(filters) if filters else None

    # Search
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=qdrant_filter,
        limit=top_k,
        with_payload=True,
    )

    # Format results
    formatted = []
    for hit in results:
        record = dict(hit.payload)
        record.pop("_embedded_text", None)  # Remove internal field
        record["_similarity_score"] = round(hit.score, 4)
        formatted.append(record)

    logger.info(f"Search for '{query[:50]}...' returned {len(formatted)} results")
    return formatted


def get_all_records(client: QdrantClient | None = None) -> List[Dict]:
    """Retrieve all records from Qdrant (for display/export)."""
    if client is None:
        client = get_qdrant_client()

    # Scroll through all points
    records = []
    offset = None

    while True:
        result = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=50,
            offset=offset,
            with_payload=True,
        )
        points, next_offset = result

        for point in points:
            record = dict(point.payload)
            record.pop("_embedded_text", None)
            record["_id"] = point.id
            records.append(record)

        if next_offset is None:
            break
        offset = next_offset

    return records


def get_record_by_id(record_id: int, client: QdrantClient | None = None) -> Optional[Dict]:
    """Get a single record by its Qdrant point ID."""
    if client is None:
        client = get_qdrant_client()

    try:
        points = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[record_id],
            with_payload=True,
        )
        if points:
            record = dict(points[0].payload)
            record.pop("_embedded_text", None)
            record["_id"] = points[0].id
            return record
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve record {record_id}: {e}")
        return None


def _build_filter(filters: Dict) -> Optional[Filter]:
    """Convert a simple filter dict to Qdrant Filter object."""
    conditions = []

    for key, value in filters.items():
        if value is None:
            continue

        if key in ("entity_type", "hq_country", "hq_state", "url_quality"):
            conditions.append(FieldCondition(
                key=key,
                match=MatchValue(value=value),
            ))
        elif key == "min_confidence":
            conditions.append(FieldCondition(
                key="confidence_score",
                range=Range(gte=float(value)),
            ))
        elif key == "min_completeness":
            conditions.append(FieldCondition(
                key="data_completeness_score",
                range=Range(gte=float(value)),
            ))

    if not conditions:
        return None

    return Filter(must=conditions)
