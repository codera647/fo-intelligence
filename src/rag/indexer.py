"""Qdrant indexer — creates collection and upserts FO record vectors."""

import logging
from typing import List, Dict
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range,
    PayloadSchemaType,
)

from config.settings import (
    QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME, EMBEDDING_DIM,
)
from .embedder import create_embeddings_batch, record_to_text

logger = logging.getLogger(__name__)


def get_qdrant_client() -> QdrantClient:
    """Create a Qdrant client connected to our cloud cluster."""
    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
    )


def create_collection(client: QdrantClient | None = None) -> None:
    """Create the family_offices collection in Qdrant (idempotent)."""
    if client is None:
        client = get_qdrant_client()

    collections = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME in collections:
        logger.info(f"Collection '{COLLECTION_NAME}' already exists, recreating...")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=EMBEDDING_DIM,
            distance=Distance.COSINE,
        ),
    )

    # Create payload indexes for structured filtering
    for field, schema_type in [
        ("entity_type", PayloadSchemaType.KEYWORD),
        ("hq_country", PayloadSchemaType.KEYWORD),
        ("hq_state", PayloadSchemaType.KEYWORD),
        ("investing_sectors", PayloadSchemaType.TEXT),
        ("url_quality", PayloadSchemaType.KEYWORD),
        ("data_completeness_score", PayloadSchemaType.FLOAT),
        ("confidence_score", PayloadSchemaType.FLOAT),
    ]:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema_type,
            )
        except Exception as e:
            logger.warning(f"Index creation for {field} failed: {e}")

    logger.info(f"Created collection '{COLLECTION_NAME}' with {EMBEDDING_DIM}d vectors")


def index_records(records: List[Dict], client: QdrantClient | None = None) -> int:
    """Embed and upsert all records into Qdrant.

    Each record becomes one point:
      - vector: embedding of natural-language record text
      - payload: full record dict (for structured filtering + retrieval)
    """
    if client is None:
        client = get_qdrant_client()

    # Convert records to text for embedding
    texts = [record_to_text(r) for r in records]

    logger.info(f"Creating embeddings for {len(texts)} records...")
    embeddings = create_embeddings_batch(texts)

    # Build Qdrant points
    points = []
    for i, (record, embedding, text) in enumerate(zip(records, embeddings, texts)):
        payload = {**record, "_embedded_text": text}
        points.append(PointStruct(
            id=i + 1,
            vector=embedding,
            payload=payload,
        ))

    # Upsert in batches
    batch_size = 20
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch,
        )

    count = client.count(collection_name=COLLECTION_NAME).count
    logger.info(f"Indexed {count} records into Qdrant")
    return count
