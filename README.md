# FO Intelligence — Family Office Intelligence Pipeline

A full-stack AI system that discovers, enriches, validates, and serves 50 real Family Office records through a Micro-RAG pipeline with natural language querying.

**Live Demo:** [https://fo-intelligence.onrender.com](https://fo-intelligence.onrender.com)

## Architecture

```
Web Sources (SEC EDGAR, Google News, Curated Seeds)
    ↓
Discovery Pipeline (multi-channel candidate sourcing)
    ↓
Enrichment Pipeline (website scraping + LLM extraction)
    ↓
Validation Layer (URL verification, confidence scoring)
    ↓
Dataset (50 validated records × 30 columns)
    ↓
Embedding (OpenAI text-embedding-3-small)
    ↓
Vector Database (Qdrant Cloud)
    ↓
RAG API (FastAPI + GPT-4o-mini generation)
    ↓
Web Interface (React + Tailwind CSS)
```

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend | FastAPI | Async Python, auto-docs, fast |
| LLM | OpenAI GPT-4o-mini | Cost-effective, fast for extraction |
| Embeddings | text-embedding-3-small | 1536d, good quality/cost ratio |
| Vector DB | Qdrant Cloud | Free tier, payload filtering |
| Frontend | React + Tailwind | Single-file SPA, no build step |
| Deployment | Render | Free tier, Python-native |

## Dataset Schema (30 Columns)

**Tier 1 — Entity Core (14):** family_office_name, entity_type, description, year_founded, aum_estimated, aum_source, investment_thesis, investing_sectors, website_url, url_quality, corporate_linkedin_url, hq_city, hq_state, hq_country

**Tier 2 — Principal Intelligence (8):** contact_name, contact_title, contact_linkedin, contact_email, email_confidence, email_source, contact_phone, phone_source

**Tier 3 — Entity Signals (4):** recent_activity, activity_date, activity_source_url, key_investments

**Tier 4 — Data Quality (4):** data_completeness_score, confidence_score, primary_sources, verification_notes

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/fo-intelligence.git
cd fo-intelligence
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Run pipeline (generates dataset + indexes to Qdrant)
python run_pipeline.py

# 4. Test RAG
python test_rag.py

# 5. Start server
uvicorn src.api.main:app --reload --port 8000
```

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

## Project Structure

```
fo-intelligence/
├── config/
│   ├── settings.py      # Environment config
│   ├── schema.py        # 30-column Pydantic model
│   └── prompts.py       # LLM prompt templates
├── src/
│   ├── discovery/       # Multi-channel FO discovery
│   ├── enrichment/      # Website scraping + LLM extraction
│   ├── validation/      # Verification + export
│   ├── rag/             # Embedding, indexing, retrieval, generation
│   └── api/             # FastAPI endpoints
├── frontend/build/      # React SPA
├── data/processed/      # Generated dataset
├── run_pipeline.py      # Main pipeline runner
├── test_rag.py          # RAG test suite
└── requirements.txt
```

## What Works Well

- Website scraping + LLM extraction produces structured data from unstructured sites
- Curated seed list ensures high-quality, real family offices
- Confidence scoring distinguishes verified data from LLM-inferred data
- Honest blanks over fabricated data — missing fields are left null with notes

## What Could Be Improved

- Add LinkedIn scraping agent for principal intelligence
- Implement multi-agent verification (cross-source consensus)
- Add scheduled re-crawling for activity signals
- Implement email verification via Hunter.io / Apollo
- Add more discovery channels (ProPublica, Crunchbase)

## License

Assessment project — not for production use.
