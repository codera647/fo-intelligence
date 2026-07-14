"""Main pipeline runner — Discovery → Enrichment → Validation → Export → Index.

Run this once to generate the 50-record dataset and index it into Qdrant.

Usage:
    python run_pipeline.py
"""

import sys
import json
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import PROCESSED_DIR
from src.discovery.discovery_pipeline import run_discovery
from src.enrichment.enrichment_pipeline import run_enrichment
from src.validation.validator import validate_records, export_to_xlsx, export_to_csv, generate_stats
from src.rag.indexer import create_collection, index_records

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("FO Intelligence Pipeline — Starting")
    logger.info("=" * 60)

    # ── Output paths (used by incremental saver) ───────────────────
    xlsx_path = PROCESSED_DIR / "family_offices_dataset.xlsx"
    csv_path = PROCESSED_DIR / "family_offices_dataset.csv"

    # ── Step 1: Discovery ──────────────────────────────────────────
    logger.info("\n>>> STEP 1: DISCOVERY")
    candidates = run_discovery(target_candidates=100)
    logger.info(f"Discovery complete: {len(candidates)} candidates")

    # ── Step 2: Enrichment (with incremental save) ─────────────────
    logger.info("\n>>> STEP 2: ENRICHMENT")

    def _save_incremental(record, all_records):
        """Validate + export after every new record so progress is never lost."""
        cleaned = validate_records(list(all_records))
        # CSV is never locked by Excel, so always succeeds
        export_to_csv(cleaned, csv_path)
        try:
            export_to_xlsx(cleaned, xlsx_path)
            logger.info(f"  >> Saved {len(cleaned)} records to {xlsx_path.name}")
        except PermissionError:
            logger.warning(
                f"  >> XLSX locked (open in Excel?) — skipped incremental save. "
                f"CSV still updated ({csv_path.name})."
            )

    enriched = run_enrichment(
        candidates,
        target=60,
        on_record_complete=_save_incremental,
    )
    logger.info(f"Enrichment complete: {len(enriched)} enriched records")

    # ── Step 3: Final validation ───────────────────────────────────
    logger.info("\n>>> STEP 3: VALIDATION")
    validated = validate_records(enriched)
    logger.info(f"Validation complete: {len(validated)} validated records")

    # Take top 50
    final_records = validated[:50]
    logger.info(f"Final dataset: {len(final_records)} records")

    # ── Step 4: Final export (top-50, sorted by confidence) ────────
    logger.info("\n>>> STEP 4: FINAL EXPORT")
    export_to_csv(final_records, csv_path)
    logger.info(f"Exported to: {csv_path}")

    # XLSX may be locked by Excel — retry up to 5 times
    for attempt in range(1, 6):
        try:
            export_to_xlsx(final_records, xlsx_path)
            logger.info(f"Exported to: {xlsx_path}")
            break
        except PermissionError:
            if attempt < 5:
                logger.warning(
                    f"XLSX locked by another process — retry {attempt}/5 in 3s "
                    f"(close the file in Excel to fix)"
                )
                time.sleep(3)
            else:
                logger.error(
                    f"Could not write XLSX after 5 attempts — file is locked. "
                    f"Close it in Excel and re-run, or use the CSV at {csv_path}"
                )

    # Save stats
    stats = generate_stats(final_records)
    stats_path = PROCESSED_DIR / "dataset_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    logger.info(f"Stats saved to: {stats_path}")

    # ── Step 5: Index into Qdrant ──────────────────────────────────
    logger.info("\n>>> STEP 5: INDEXING INTO QDRANT")
    create_collection()
    count = index_records(final_records)
    logger.info(f"Indexed {count} records into Qdrant")

    # ── Summary ────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Records: {len(final_records)}")
    logger.info(f"  Avg Completeness: {stats['avg_completeness']}%")
    logger.info(f"  Avg Confidence: {stats['avg_confidence']}%")
    logger.info(f"  Entity Types: {stats.get('entity_types', {})}")
    logger.info(f"  Dataset: {xlsx_path}")
    logger.info("=" * 60)

    return final_records


if __name__ == "__main__":
    main()
