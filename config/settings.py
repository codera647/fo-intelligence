"""Central configuration — loads .env and exposes typed settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── paths ──────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

for d in [DATA_DIR, RAW_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── env ────────────────────────────────────────────────────────────
load_dotenv(ROOT_DIR / ".env")

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# Brave Search
BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")

# Qdrant
QDRANT_URL: str = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "family_offices")

# OpenRouter (for FO classification)
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")

# Google Custom Search (for LinkedIn discovery) — legacy, kept for reference
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CX: str = os.getenv("GOOGLE_CX", "")

# Tavily Search API (primary search backend for Stage 4)
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# Models
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM: int = 1536  # text-embedding-3-small dimension
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

# RAG
TOP_K: int = int(os.getenv("TOP_K", "15"))

# Discovery
MAX_CANDIDATES: int = 150
TARGET_RECORDS: int = 50

# Pipeline intermediate files
PIPELINE_DIR = DATA_DIR / "pipeline"
PIPELINE_DIR.mkdir(parents=True, exist_ok=True)

# Rate limits
REQUEST_DELAY: float = 1.0  # seconds between web requests
