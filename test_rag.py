"""Test the RAG pipeline after indexing — run sample queries."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.rag.generator import query_rag
from src.rag.retriever import get_all_records

def main():
    # Check collection has data
    records = get_all_records()
    print(f"\n{'='*60}")
    print(f"Total records in Qdrant: {len(records)}")
    print(f"{'='*60}\n")

    if not records:
        print("ERROR: No records found in Qdrant. Run run_pipeline.py first.")
        return

    # Test queries
    test_queries = [
        "Family offices investing in AI and technology",
        "Single family offices based in New York",
        "Family offices with large AUM",
        "Multi family offices focused on healthcare",
        "Family offices active in real estate",
    ]

    for q in test_queries:
        print(f"\n{'─'*60}")
        print(f"Query: {q}")
        print(f"{'─'*60}")

        result = query_rag(question=q, top_k=3)
        print(f"\nAnswer:\n{result['answer'][:500]}")
        print(f"\nRecords returned: {len(result['records'])}")
        for r in result['records']:
            print(f"  - {r.get('family_office_name')} (score: {r.get('_similarity_score', 'N/A')})")

    print(f"\n{'='*60}")
    print("RAG test complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
