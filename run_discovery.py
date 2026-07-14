"""Stage 1 runner — PipelineRoad discovery only.

Scrapes ~130 family offices from PipelineRoad's LP directory,
fetches each detail page for website URLs and investment data,
and saves everything to data/pipeline/01_discovered_family_offices.json.

Supports resuming: re-run safely if interrupted.

Usage:
    python run_discovery.py
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import PIPELINE_DIR
from src.discovery.pipelineroad_scraper import run_pipelineroad_discovery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    output_path = PIPELINE_DIR / "01_discovered_family_offices.json"
    records = run_pipelineroad_discovery(output_path)
    print(f"\nDone! {len(records)} family offices -> {output_path}")
