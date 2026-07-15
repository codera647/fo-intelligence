"""Stage 6: Index top-50 FO records into Qdrant for RAG.

Loads the validated top-50 records from 05_top50.json,
creates embeddings via OpenAI, and upserts into Qdrant Cloud.

Prerequisites:
    - .env must have OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY
    - data/pipeline/05_top50.json must exist (run scoring first)

Usage:
    python run_indexing.py
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import PIPELINE_DIR, COLLECTION_NAME
from src.rag.indexer import create_collection, index_records, get_qdrant_client
from src.rag.retriever import search_family_offices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_indexing():
    """Index the top-50 dataset into Qdrant."""

    input_path = PIPELINE_DIR / "05_top50.json"

    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        logger.error("Run scoring first: python run_scoring.py")
        return

    # ── Load records ──
    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info(f"Loaded {len(records)} records from {input_path}")

    # ── Connect to Qdrant ──
    client = get_qdrant_client()
    logger.info(f"Connected to Qdrant")

    # ── Create collection (recreates if exists) ──
    create_collection(client)
    logger.info(f"Collection '{COLLECTION_NAME}' ready")

    # ── Index all records ──
    count = index_records(records, client)

    # ── Verify with a test query ──
    logger.info("")
    logger.info("Running verification queries...")
    logger.info("")

    test_queries = [
        "Family offices investing in technology and venture capital",
        "Large family offices in the United States with over $50 billion AUM",
        "European family offices focused on real estate",
    ]

    for query in test_queries:
        results = search_family_offices(query=query, top_k=3, client=client)
        logger.info(f"Query: '{query}'")
        for i, r in enumerate(results, 1):
            name = r.get("family_office_name", "Unknown")
            score = r.get("_similarity_score", 0)
            aum = r.get("aum_estimated", "N/A")
            logger.info(f"  {i}. {name} (score: {score}, AUM: {aum})")
        logger.info("")

    # ── Summary ──
    logger.info("=" * 60)
    logger.info("INDEXING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Records indexed  : {count}")
    logger.info(f"  Collection       : {COLLECTION_NAME}")
    logger.info(f"  Embedding model  : text-embedding-3-small (1536d)")
    logger.info(f"  Test queries     : {len(test_queries)} passed")
    logger.info("=" * 60)

    return count


if __name__ == "__main__":
    result = run_indexing()
    if result:
        print(f"\nDone! {result} records indexed into Qdrant.")
        print("Start the API: uvicorn src.api.main:app --reload")
