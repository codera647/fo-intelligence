"""Stage 4 runner — Google Search Contact Discovery.

Three-tier contact enrichment:
  Tier 1 — Has team + partial contacts → fill gaps
  Tier 2 — Has team names, no contacts → find both
  Tier 3 — No team at all → discover people + contacts

Processes FOs in priority order: Tier 1 (cheapest) → Tier 2 → Tier 3.
Saves progress every 5 FOs so you can resume after interruption.

Input:  data/pipeline/02_enriched_family_offices.json
Output: data/pipeline/03_contacts_enriched.json

Usage:
    python run_contact_search.py
"""

import sys
import json
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import PIPELINE_DIR
from src.enrichment.google_contact_search import (
    enrich_fo_contacts,
    classify_tier,
    get_query_count,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _save_json(data: list, path: Path) -> None:
    """Save list of records to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_contact_search():
    """Full Stage 4: tiered Google Search contact discovery."""

    input_path = PIPELINE_DIR / "02_enriched_family_offices.json"
    output_path = PIPELINE_DIR / "03_contacts_enriched.json"

    # ── Load enriched FOs ──
    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        logger.error("Run Stage 2+3 first: python run_enrichment.py")
        return []

    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info("=" * 60)
    logger.info("STAGE 4: Google Search Contact Discovery")
    logger.info("=" * 60)
    logger.info(f"Loaded {len(records)} FOs from Stage 2+3")

    # ── Check for resume state ──
    already_done: set[str] = set()
    done_records: dict[str, dict] = {}

    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        for rec in existing:
            slug = rec.get("slug", "")
            # Only skip if truly processed (has tier AND no error)
            if (rec.get("contact_enrichment_tier") is not None
                    and not rec.get("contact_enrichment_error")):
                already_done.add(slug)
                done_records[slug] = rec
        if already_done:
            logger.info(f"Resuming — {len(already_done)} FOs already processed")

    # ── Classify all FOs into tiers ──
    tier_map: dict[int, list[dict]] = {1: [], 2: [], 3: []}

    for rec in records:
        slug = rec.get("slug", "")
        if slug in already_done:
            continue
        tier, _ = classify_tier(rec)
        tier_map[tier].append(rec)

    total_todo = sum(len(v) for v in tier_map.values())

    logger.info(f"To process: {total_todo}")
    logger.info(f"  Tier 1 (fill gaps)      : {len(tier_map[1])}")
    logger.info(f"  Tier 2 (find contacts)  : {len(tier_map[2])}")
    logger.info(f"  Tier 3 (discover team)  : {len(tier_map[3])}")
    logger.info(f"  Already done            : {len(already_done)}")
    logger.info("")

    if total_todo == 0:
        logger.info("Nothing to process — all FOs already have contact enrichment.")
        return list(done_records.values())

    # ── Process in tier order (cheapest first) ──
    results: list[dict] = []
    processed = 0
    start_time = time.time()

    for tier_num in [1, 2, 3]:
        tier_fos = tier_map[tier_num]
        if not tier_fos:
            continue

        logger.info("=" * 60)
        logger.info(f"TIER {tier_num}: Processing {len(tier_fos)} FOs")
        logger.info("=" * 60)

        for i, fo in enumerate(tier_fos):
            processed += 1
            name = fo.get("name", "Unknown")
            logger.info(f"[{processed}/{total_todo}] {name}")

            try:
                enriched = enrich_fo_contacts(fo)
                results.append(enriched)
            except Exception as e:
                logger.error(f"  ERROR: {e}")
                fo["contact_enrichment_tier"] = tier_num
                fo["contact_enrichment_error"] = str(e)
                results.append(fo)

            # Rate limiting between FOs
            time.sleep(0.5)

            # Incremental save every 5 FOs
            if processed % 5 == 0:
                _save_progress(records, results, done_records, output_path)
                queries = get_query_count()
                elapsed = time.time() - start_time
                logger.info(
                    f"  >> Saved ({processed}/{total_todo}) | "
                    f"{queries} queries | {elapsed:.0f}s elapsed"
                )

    # ── Final merge and save ──
    _save_progress(records, results, done_records, output_path)

    elapsed = time.time() - start_time
    queries = get_query_count()

    # ── Stats ──
    all_out = _build_final_list(records, results, done_records)

    total = len(all_out)
    w_team = sum(1 for r in all_out if r.get("team_members"))
    w_linkedin = sum(
        1 for r in all_out
        if any(
            (m.get("linkedin_url") or "").startswith("http")
            for m in r.get("team_members", [])
        )
    )
    w_email = sum(
        1 for r in all_out
        if any(
            (m.get("email") or "") and "@" in (m.get("email") or "")
            for m in r.get("team_members", [])
        )
    )
    w_corp_li = sum(1 for r in all_out if r.get("corporate_linkedin"))

    logger.info("")
    logger.info("=" * 60)
    logger.info("STAGE 4 COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Total FOs              : {total}")
    logger.info(f"  Tavily queries used    : {queries}")
    logger.info(f"  Time elapsed           : {elapsed:.1f}s")
    logger.info(f"  With team members      : {w_team}")
    logger.info(f"  With person LinkedIn   : {w_linkedin}")
    logger.info(f"  With person email      : {w_email}")
    logger.info(f"  With corporate LinkedIn: {w_corp_li}")
    logger.info(f"  Saved to               : {output_path}")
    logger.info("=" * 60)

    return all_out


def _build_final_list(
    original: list[dict],
    new_results: list[dict],
    done_records: dict[str, dict],
) -> list[dict]:
    """Build the final ordered list: new results + resumed records + un-processed."""
    result_map: dict[str, dict] = {}

    # Start with previously-done records
    for slug, rec in done_records.items():
        result_map[slug] = rec

    # Layer on new results
    for rec in new_results:
        slug = rec.get("slug", "")
        result_map[slug] = rec

    # Build final list in original order, filling any gaps
    final = []
    for rec in original:
        slug = rec.get("slug", "")
        if slug in result_map:
            final.append(result_map[slug])
        else:
            # Un-processed FO — pass through unchanged
            final.append(rec)

    return final


def _save_progress(
    original: list[dict],
    new_results: list[dict],
    done_records: dict[str, dict],
    output_path: Path,
) -> None:
    """Save current progress to disk."""
    final = _build_final_list(original, new_results, done_records)
    _save_json(final, output_path)


if __name__ == "__main__":
    results = run_contact_search()
    print(f"\nDone! {len(results)} FOs → {PIPELINE_DIR / '03_contacts_enriched.json'}")
