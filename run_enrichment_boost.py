"""Stage 4.5 runner — Enrichment Boost.

Applies quality improvements to the contact-enriched dataset:
  1. MX email verification (Medium → High confidence)
  2. Recent activity discovery via Tavily
  3. Email discovery for contacts with LinkedIn but no email
  4. Deduplication of known duplicate FOs
  5. Placeholder contact cleanup
  6. Country mapping fix for non-US FOs

Then re-runs Stage 5 (scoring + top-50 selection) automatically.

Input:  data/pipeline/03_contacts_enriched.json
Output: data/pipeline/03_contacts_enriched.json  (overwritten)
        data/pipeline/04_scored.json             (re-scored)
        data/pipeline/05_top50.json              (re-selected)
        data/processed/family_offices_dataset.xlsx
        data/processed/family_offices_dataset.csv

Usage:
    python run_enrichment_boost.py                  # Full run
    python run_enrichment_boost.py --skip-tavily    # MX + cleanup only (no API cost)
"""

import sys
import json
import shutil
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import PIPELINE_DIR, PROCESSED_DIR
from src.enrichment.enrichment_boost import boost_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _save_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_boost(skip_tavily: bool = False):
    """Stage 4.5: boost data quality, then re-run Stage 5."""

    input_path = PIPELINE_DIR / "03_contacts_enriched.json"
    backup_path = PIPELINE_DIR / "03_contacts_enriched.backup.json"

    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        logger.error("Run Stage 4 first: python run_contact_search.py")
        return

    # ── Load ──
    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info(f"Loaded {len(records)} FOs from {input_path}")

    # ── Backup original ──
    shutil.copy2(input_path, backup_path)
    logger.info(f"Backup saved → {backup_path}")

    # ── Run all boosts ──
    boosted = boost_all(
        records,
        skip_tavily=skip_tavily,
        max_activity_queries=60,
        max_email_queries=40,
    )

    # ── Save boosted records ──
    _save_json(boosted, input_path)
    logger.info(f"Saved boosted records → {input_path} ({len(boosted)} FOs)")

    # ── Re-run Stage 5 (scoring) ──
    logger.info("")
    logger.info("Re-running Stage 5: Scoring + Top-50 Selection...")
    logger.info("")

    from src.validation.fo_scorer import score_and_rank
    from src.validation.validator import (
        validate_records,
        export_to_xlsx,
        export_to_csv,
        generate_stats,
    )

    all_scored, top50_export = score_and_rank(boosted, top_n=50)

    # Save scored (slim)
    scored_path = PIPELINE_DIR / "04_scored.json"
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

    # Save top 50
    top50_path = PIPELINE_DIR / "05_top50.json"
    _save_json(top50_export, top50_path)

    # Validate + export
    validated = validate_records(top50_export)
    xlsx_path = export_to_xlsx(validated)
    csv_path = export_to_csv(validated)
    stats = generate_stats(validated)

    # ── Summary ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("STAGE 4.5 + 5 COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  FOs after dedup        : {len(boosted)}")
    logger.info(f"  Top 50 selected        : {len(validated)}")
    logger.info(f"  Avg quality score      : {stats.get('avg_confidence', 0):.1f}")
    logger.info(f"  Avg completeness       : {stats.get('avg_completeness', 0):.1f}%")
    logger.info(f"  Records with email     : {stats.get('records_with_email', 0)}")
    logger.info(f"  Records with LinkedIn  : {stats.get('records_with_linkedin', 0)}")

    # Email confidence distribution
    email_dist = stats.get("email_confidence_dist", {})
    if email_dist:
        logger.info(f"  Email confidence dist  : {email_dist}")

    logger.info(f"  XLSX                   : {xlsx_path}")
    logger.info(f"  CSV                    : {csv_path}")
    logger.info("=" * 60)

    # Score distribution
    logger.info("")
    logger.info("Score distribution (top 50):")
    brackets = {"85+": 0, "70-84": 0, "60-69": 0, "50-59": 0, "<50": 0}
    for r in validated:
        s = r.get("confidence_score") or 0
        if s >= 85:
            brackets["85+"] += 1
        elif s >= 70:
            brackets["70-84"] += 1
        elif s >= 60:
            brackets["60-69"] += 1
        elif s >= 50:
            brackets["50-59"] += 1
        else:
            brackets["<50"] += 1

    for bracket, count in brackets.items():
        bar = "█" * count
        logger.info(f"  {bracket:>6}: {count:3d} {bar}")

    return validated


if __name__ == "__main__":
    skip = "--skip-tavily" in sys.argv
    if skip:
        print("Running in offline mode (MX + cleanup only, no Tavily queries)")

    results = run_boost(skip_tavily=skip)
    if results:
        print(f"\nDone! {len(results)} records exported.")
        print(f"  XLSX: {PROCESSED_DIR / 'family_offices_dataset.xlsx'}")
        print(f"  CSV:  {PROCESSED_DIR / 'family_offices_dataset.csv'}")
