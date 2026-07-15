# FO Intelligence — Family Office Intelligence Pipeline

A full-stack AI system that discovers, enriches, scores, and serves **50 Family Office records** through a Micro-RAG pipeline with natural language querying.

**Live Demo:** [https://fo-intelligence.onrender.com](https://fo-intelligence.onrender.com)

## Architecture

```
PipelineRoad LP directory  (Stage 1 — discovery)
    ↓
Website crawl + GPT extraction  (Stage 2/3 — Crawl4AI + GPT-4o-mini)
    ↓
Contact discovery  (Stage 4 — Tavily search + email-pattern inference)
    ↓
Enrichment boost  (Stage 4.5 — MX verification, recent activity, dedup, cleanup)
    ↓
Quality scoring + Top-50 selection  (Stage 5 — analytical, 0-100)
    ↓
Dataset (50 records × 28 columns → CSV / XLSX)
    ↓
Embedding (OpenAI text-embedding-3-small, 1536d)
    ↓
Vector Database (Qdrant Cloud)  (Stage 6 — indexing)
    ↓
RAG API (FastAPI + GPT-4o-mini generation)
    ↓
Web Interface (React + Tailwind CSS)
```

> **Note on data provenance.** The dataset is a best-effort research artifact, not a
> verified contact database. Entity/AUM data originates from the PipelineRoad LP
> directory and website crawls. **Contact emails and personal LinkedIn URLs are largely
> pattern-inferred** (`first.last@domain`) and validated only at the *domain* level via
> MX records — the domain accepts mail, but the specific address is **not** confirmed to
> belong to the named person. See [Data Quality & Confidence](#data-quality--confidence).

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend | FastAPI | Async Python, auto-docs, fast |
| LLM | OpenAI GPT-4o-mini | Cost-effective, fast for extraction |
| Embeddings | text-embedding-3-small | 1536d, good quality/cost ratio |
| Vector DB | Qdrant Cloud | Free tier, payload filtering |
| Crawling | Crawl4AI (headless Chromium) | JS-rendered sites + bot-protection fallback |
| Contact search | Tavily Search API | Programmatic web search for people/contacts |
| Frontend | React + Tailwind | Single-file SPA, no build step |
| Deployment | Render | Free tier, Python-native |

## Dataset Schema (28 Columns)

**Tier 1 — Entity Core (16):** family_office_name, entity_type, description, year_founded, aum_estimated, aum_source, investment_thesis, investing_sectors, website_url, url_quality, corporate_linkedin_url, corporate_email, other_socials, hq_city, hq_state, hq_country

**Tier 2 — Principal Intelligence (6):** contact_name, contact_title, contact_linkedin, contact_email, email_confidence, email_source

**Tier 3 — Entity Signals (4):** recent_activity, activity_date, activity_source_url, key_investments

**Tier 4 — Data Quality (2):** data_completeness_score, confidence_score

The canonical schema lives in [`config/schema.py`](config/schema.py) (`COLUMN_ORDER`).

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/codera647/fo-intelligence.git
cd fo-intelligence
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys (OpenAI, Qdrant, Tavily, optionally Brave/OpenRouter)

# 3. Serve the shipped dataset (index + API)
#    The generated dataset is committed under data/processed/, so you can index
#    and serve it directly without re-running the full crawl:
python run_indexing.py          # embeds data/pipeline/05_top50.json → Qdrant
uvicorn src.api.main:app --reload --port 8000

# 4. (Optional) test the RAG stack
python test_rag.py
```

### Regenerating the dataset from scratch

The pipeline runs as ordered stages, each reading the previous stage's JSON from
`data/pipeline/` and safe to resume if interrupted:

```bash
python run_discovery.py         # Stage 1 → 01_discovered_family_offices.json
python run_enrichment.py        # Stage 2/3 (Crawl4AI + GPT) → 02_enriched...json
python run_contact_search.py    # Stage 4 (Tavily) → 03_contacts_enriched.json
python run_enrichment_boost.py  # Stage 4.5 (+ re-runs scoring/export)
python run_scoring.py           # Stage 5 → 04_scored.json, 05_top50.json, CSV/XLSX
python run_indexing.py          # Stage 6 → Qdrant
```

> Only `01_discovered_family_offices.json` and the final `data/processed/` exports are
> committed. Stages 2–5 regenerate their intermediates on the fly; `run_indexing.py`
> requires `05_top50.json`, produced by `run_scoring.py` (or `run_enrichment_boost.py`).
> Stage 2 additionally needs `crawl4ai` + a Chromium runtime installed.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/query` | POST | RAG query (question → AI answer + records) |
| `/api/search?q=` | GET | Semantic search (records only) |
| `/api/records` | GET | List all records |
| `/api/records/{id}` | GET | Single record detail |
| `/api/stats` | GET | Dataset statistics |

## RAG Approach

**Semantic Search + Structured Filtering** (not hybrid BM25):
- Each FO record is converted to natural language text and embedded
- Queries are embedded and matched via cosine similarity in Qdrant
- Qdrant payload filters enable structured queries (entity_type, country, etc.)
- Retrieved records are passed to GPT-4o-mini for natural language answer generation

This approach is optimal for 50 records — BM25 adds complexity without benefit at this scale.

## Data Quality & Confidence

Two per-record scores are exported, and they measure **different** things:

- **`data_completeness_score` (0–100)** — the share of the 28 columns that are populated.
- **`confidence_score` (0–100)** — an *analytical quality/richness* score computed by
  [`fo_scorer.py`](src/validation/fo_scorer.py) from data signals (contact quality,
  entity intelligence, team discovery, corporate presence, completeness). **It reflects
  how much structured data was assembled, not independent verification of that data.**

**`email_confidence`** describes how each contact email was obtained:
- `High` — pattern-inferred and passed MX (domain-level) validation
- `Medium` — pattern-inferred from the corporate domain, not MX-checked
- `Low` — generic address scraped from the website
- `Not Found` — no email

Because emails/LinkedIn are inferred rather than confirmed at the individual level, treat
them as **leads to verify**, not ground truth.

## Project Structure

```
fo-intelligence/
├── config/
│   ├── settings.py      # Environment config
│   ├── schema.py        # 28-column Pydantic model + COLUMN_ORDER
│   └── prompts.py       # RAG prompt templates
├── src/
│   ├── discovery/       # pipelineroad_scraper (Stage 1)
│   ├── enrichment/      # website_crawler, gpt_extractor, google_contact_search,
│   │                    #   enrichment_boost (Stages 2–4.5)
│   ├── validation/      # fo_scorer (Stage 5) + validator (clean/export)
│   ├── rag/             # Embedding, indexing, retrieval, generation
│   └── api/             # FastAPI endpoints + static frontend serving
├── frontend/build/      # React SPA (Chat + Explorer)
├── data/
│   ├── pipeline/        # Stage JSON intermediates (01 committed)
│   └── processed/       # Final CSV / XLSX / stats
├── run_discovery.py … run_indexing.py   # Ordered stage runners
├── tag_enriched_sources.py              # Provenance-tagging utility
├── test_rag.py                          # RAG smoke test
└── requirements.txt
```

## What Works Well

- Website crawl + GPT extraction produces structured data from unstructured sites
- Confidence and completeness scoring make the data-richness of each record explicit
- Staged, resumable pipeline — every stage can be re-run without losing prior work
- Semantic RAG over a compact, curated set gives fast, relevant answers

## What Could Be Improved

- **Verify contacts for real** (Hunter.io / Apollo) instead of pattern-inferring emails
- Add a LinkedIn scraping agent for genuine principal intelligence
- Replace the single-directory (PipelineRoad) discovery source with multiple channels
- Fill the ~10 records missing `entity_type` and other Tier-1 gaps
- Implement multi-agent / cross-source consensus verification
- Add scheduled re-crawling for fresh activity signals

## License

Assessment project — not for production use.
