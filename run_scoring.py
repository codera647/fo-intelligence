"""Stage 5 runner — Quality Scoring + Top-50 Selection.

Scores all enriched FOs on a 0-100 scale using existing data signals
(zero additional API queries), selects the top 50, maps them to the
28-column export schema, and exports as JSON / CSV / XLSX.

Input:  data/pipeline/03_contacts_enriched.json
Output: data/pipeline/04_scored.json        (all FOs with scores)
        data/pipeline/05_top50.json          (top 50 in export schema)
        data/processed/family_offices_dataset.xlsx
        data/processed/family_offices_dataset.csv

Usage:
    python run_scoring.py
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import PIPELINE_DIR, PROCESSED_DIR
from src.validation.fo_scorer import score_and_rank
from src.validation.validator import (
    validate_records,
    export_to_xlsx,
    export_to_csv,
    generate_stats,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _save_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_scoring():
    """Full Stage 5: score, rank, select top 50, export."""

    input_path = PIPELINE_DIR / "03_contacts_enriched.json"
    scored_path = PIPELINE_DIR / "04_scored.json"
    top50_path = PIPELINE_DIR / "05_top50.json"

    # ── Load ──
    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        logger.error("Run Stage 4 first: python run_contact_search.py")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info("=" * 60)
    logger.info("STAGE 5: Quality Scoring + Top-50 Selection")
    logger.info("=" * 60)
    logger.info(f"Loaded {len(records)} FOs from Stage 4")

    # ── Score and rank ──
    all_scored, top50_export = score_and_rank(records, top_n=50)

    # ── Save scored (full) ──
    # Strip non-serializable bits for JSON output
    scored_for_json = []
    for rec in all_scored:
        slim = {
            "name": rec.get("name"),
            "slug": rec.get("slug"),
            "quality_score": rec.get("quality_score"),
            "score_breakdown": rec.get("score_breakdown"),
            "best_contact_name": rec.get("best_contact_name"),
            "best_contact_title": rec.get("best_contact_title"),
            "best_contact_email": rec.get("best_contact_email"),
            "best_contact_linkedin": rec.get("best_contact_linkedin"),
            "best_email_confidence": rec.get("best_email_confidence"),
            "contact_enrichment_tier": rec.get("contact_enrichment_tier"),
            "crawl_status": rec.get("crawl_status"),
        }
        scored_for_json.append(slim)

    _save_json(scored_for_json, scored_path)
    logger.info(f"Saved all scores → {scored_path}")

    # ── Save top 50 (export schema) ──
    _save_json(top50_export, top50_path)
    logger.info(f"Saved top 50 (export schema) → {top50_path}")

    # ── Validate + export ──
    validated = validate_records(top50_export)

    xlsx_path = export_to_xlsx(validated)
    csv_path = export_to_csv(validated)

    # ── Stats ──
    stats = generate_stats(validated)

    logger.info("")
    logger.info("=" * 60)
    logger.info("STAGE 5 COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Total FOs scored       : {len(all_scored)}")
    logger.info(f"  Top 50 selected        : {len(validated)}")
    logger.info(f"  Avg quality score      : {stats.get('avg_confidence', 0):.1f}")
    logger.info(f"  Avg completeness       : {stats.get('avg_completeness', 0):.1f}%")
    logger.info(f"  Records with contact   : {stats.get('records_with_contact', 0)}")
    logger.info(f"  Records with email     : {stats.get('records_with_email', 0)}")
    logger.info(f"  Records with LinkedIn  : {stats.get('records_with_linkedin', 0)}")
    logger.info(f"  XLSX                   : {xlsx_path}")
    logger.info(f"  CSV                    : {csv_path}")
    logger.info("=" * 60)

    # Print score distribution
    logger.info("")
    logger.info("Score distribution (top 50):")
    brackets = {"70+": 0, "50-69": 0, "30-49": 0, "<30": 0}
    for r in validated:
        s = r.get("confidence_score") or 0
        if s >= 70:
            brackets["70+"] += 1
        elif s >= 50:
            brackets["50-69"] += 1
        elif s >= 30:
            brackets["30-49"] += 1
        else:
            brackets["<30"] += 1

    for bracket, count in brackets.items():
        bar = "█" * count
        logger.info(f"  {bracket:>6}: {count:3d} {bar}")

    return validated


if __name__ == "__main__":
    results = run_scoring()
    if results:
        print(f"\nDone! {len(results)} records exported.")
        print(f"  XLSX: {PROCESSED_DIR / 'family_offices_dataset.xlsx'}")
        print(f"  CSV:  {PROCESSED_DIR / 'family_offices_dataset.csv'}")
