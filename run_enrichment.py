"""Stage 2+3 runner — Website crawl (parallel) + GPT extraction.

Two-phase approach:
  Phase 1 (Crawl4AI): Parallel-crawl all FO websites using headless
      Chromium — homepage + priority subpages per site.
  Phase 2 (GPT):      Sequential extraction per FO — Agent A (company
      intelligence) + Agent B (people & contacts).

Input:  data/pipeline/01_discovered_family_offices.json
Output: data/pipeline/02_enriched_family_offices.json

Supports resuming: re-run safely if interrupted — already-enriched
FOs (crawl_status == "Enriched") are skipped.

Usage:
    python run_enrichment.py
"""

import sys
import json
import time
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import PIPELINE_DIR
from src.enrichment.website_crawler import crawl_all_websites_async, crawl_fo_website
from src.enrichment.gpt_extractor import extract_fo_intelligence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _save_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_enrichment():
    """Full Stage 2+3: parallel crawl → sequential GPT extraction → enriched JSON."""

    input_path = PIPELINE_DIR / "01_discovered_family_offices.json"
    output_path = PIPELINE_DIR / "02_enriched_family_offices.json"

    # ── Load discovered FOs ──
    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        logger.error("Run Stage 1 first: python run_discovery.py")
        return []

    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info("=" * 60)
    logger.info("STAGE 2+3: Website Crawl (Crawl4AI) + GPT Extraction")
    logger.info("=" * 60)
    logger.info(f"Loaded {len(records)} FOs from Stage 1")

    # ── Check for resume state ──
    enriched_records: list[dict] = []
    already_done: set[str] = set()

    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing_map = {r["slug"]: r for r in existing}
        for rec in records:
            if rec["slug"] in existing_map:
                old = existing_map[rec["slug"]]
                if old.get("crawl_status") == "Enriched":
                    enriched_records.append(old)
                    already_done.add(rec["slug"])
        if already_done:
            logger.info(f"Resuming — {len(already_done)} FOs already enriched")

    # ── Split into categories ──
    to_process = [
        r for r in records
        if r.get("website") and r["slug"] not in already_done
    ]
    no_url = [
        r for r in records
        if not r.get("website") and r["slug"] not in already_done
    ]

    total_with_url = sum(1 for r in records if r.get("website"))
    total_no_url = len(records) - total_with_url

    logger.info(f"FOs with website URL : {total_with_url}")
    logger.info(f"FOs without URL      : {total_no_url} (pass-through)")
    logger.info(f"To process this run  : {len(to_process)}")
    logger.info("")

    if not to_process:
        logger.info("Nothing to process — all FOs already enriched or have no URL.")
        # Still add no_url pass-throughs
        for rec in no_url:
            rec["crawl_status"] = "NoWebsite"
            enriched_records.append(rec)
        _save_json(enriched_records, output_path)
        return enriched_records

    # ══════════════════════════════════════════════════════════════
    # PHASE 1: Parallel website crawling via Crawl4AI
    # ══════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PHASE 1: Parallel Website Crawling (Crawl4AI)")
    logger.info("=" * 60)

    crawl_start = time.time()
    crawled_texts = asyncio.run(
        crawl_all_websites_async(to_process, already_done)
    )
    crawl_elapsed = time.time() - crawl_start

    logger.info(f"Crawling done in {crawl_elapsed:.1f}s — "
                f"{len(crawled_texts)}/{len(to_process)} sites returned content")
    logger.info("")

    # ══════════════════════════════════════════════════════════════
    # PHASE 2: Sequential GPT extraction
    # ══════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PHASE 2: GPT Extraction (Agent A + Agent B)")
    logger.info("=" * 60)

    success_count = 0
    fail_count = 0

    for i, record in enumerate(to_process):
        slug = record["slug"]
        name = record["name"]

        crawled_text = crawled_texts.get(slug)

        if not crawled_text:
            logger.warning(f"[{i+1}/{len(to_process)}] {name} — no crawled content, marking CrawlFailed")
            record["crawl_status"] = "CrawlFailed"
            enriched_records.append(record)
            fail_count += 1
            continue

        logger.info(f"[{i+1}/{len(to_process)}] {name} — {len(crawled_text):,} chars")

        try:
            enriched = extract_fo_intelligence(record, crawled_text)
            enriched["crawl_status"] = "Enriched"
            enriched["crawled_chars"] = len(crawled_text)
            enriched_records.append(enriched)
            success_count += 1
        except Exception as e:
            logger.error(f"  GPT extraction failed: {e}")
            record["crawl_status"] = "ExtractionFailed"
            enriched_records.append(record)
            fail_count += 1

        # Incremental save every 5 FOs
        if (i + 1) % 5 == 0:
            save_list = enriched_records + no_url
            _save_json(save_list, output_path)
            logger.info(f"  >> Progress saved ({i+1}/{len(to_process)})")

    # ── Add pass-through FOs (no URL) ──
    for rec in no_url:
        rec["crawl_status"] = "NoWebsite"
        enriched_records.append(rec)

    # ── Final save ──
    _save_json(enriched_records, output_path)

    # ── Stats ──
    total = len(enriched_records)
    enriched = sum(1 for r in enriched_records if r.get("crawl_status") == "Enriched")
    w_team = sum(1 for r in enriched_records if r.get("team_members"))
    w_email = sum(1 for r in enriched_records if r.get("primary_email"))
    w_sectors = sum(1 for r in enriched_records if r.get("sectors"))
    w_thesis = sum(1 for r in enriched_records
                   if r.get("website_investment_thesis") or r.get("investment_strategy"))
    w_contacts = sum(1 for r in enriched_records if r.get("best_contacts"))

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Enrichment complete: {total} total records")
    logger.info(f"  Crawl time            : {crawl_elapsed:.1f}s")
    logger.info(f"  Successfully enriched : {enriched}")
    logger.info(f"  Crawl failed          : {fail_count}")
    logger.info(f"  No website (skipped)  : {total_no_url}")
    logger.info(f"  With team members     : {w_team}")
    logger.info(f"  With email            : {w_email}")
    logger.info(f"  With sectors          : {w_sectors}")
    logger.info(f"  With investment thesis: {w_thesis}")
    logger.info(f"  With key contacts     : {w_contacts}")
    logger.info(f"  Saved to              : {output_path}")
    logger.info("=" * 60)

    return enriched_records


if __name__ == "__main__":
    results = run_enrichment()
    print(f"\nDone! {len(results)} family offices -> {PIPELINE_DIR / '02_enriched_family_offices.json'}")
