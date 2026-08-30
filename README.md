<div align="center">

# FO Intelligence

### Family Office Intelligence Pipeline — AI-Powered Discovery, Enrichment & RAG

*Automated pipeline that discovers, crawls, enriches, scores, and serves 50 Family Office records through a natural-language query interface*

[![FastAPI](https://img.shields.io/badge/FastAPI-1.0-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/GPT--4o--mini-extraction-412991?style=flat-square&logo=openai)](https://openai.com/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Cloud-DC244C?style=flat-square)](https://qdrant.tech/)
[![LangChain](https://img.shields.io/badge/LangChain-RAG-1C3C3C?style=flat-square)](https://www.langchain.com/)
[![Render](https://img.shields.io/badge/Deployed-Render-46E3B7?style=flat-square)](https://render.com/)

**Live Demo:** [https://fo-intelligence.onrender.com](https://fo-intelligence.onrender.com)

</div>

---

## What is FO Intelligence?

FO Intelligence is a full-stack AI pipeline that automates Family Office research. It:

1. **Discovers** family offices from directory listings using structured scraping
2. **Crawls** each FO's website using headless Chromium with anti-detection, extracting team pages, contact pages, and press releases
3. **Enriches** raw HTML into structured records using a two-agent GPT-4o-mini system
4. **Finds contacts** using Tavily Search to locate LinkedIn profiles and infer email addresses with MX domain verification
5. **Scores** each record on five analytical dimensions and selects the top 50 by quality
6. **Indexes** the 50 records into Qdrant Cloud using OpenAI embeddings (1536d)
7. **Serves** a FastAPI RAG endpoint and a React frontend for natural-language querying

The end result is a curated, scored, and queryable dataset of 50 family offices — each with entity intelligence, principal contacts, investment signals, and data quality scores — served through a chat interface.

> **Data Provenance Note:** Contact emails are largely pattern-inferred (`first.last@domain`) and validated at the *domain* level via MX records only. The domain accepts mail — the specific address is not individually confirmed. Treat contacts as leads to verify, not ground truth.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Pipeline Stages](#pipeline-stages)
- [File Structure](#file-structure)
- [Module Deep Dive](#module-deep-dive)
  - [Stage 1 — pipelineroad\_scraper.py](#stage-1--pipelineroad_scraperpy)
  - [Stage 2 — website\_crawler.py](#stage-2--website_crawlerpy)
  - [Stage 3 — gpt\_extractor.py](#stage-3--gpt_extractorpy)
  - [Stage 4 — google\_contact\_search.py](#stage-4--google_contact_searchpy)
  - [Stage 4.5 — enrichment\_boost.py](#stage-45--enrichment_boostpy)
  - [Stage 5 — fo\_scorer.py + validator.py](#stage-5--fo_scorerpy--validatorpy)
  - [Stage 6 — RAG Stack](#stage-6--rag-stack)
  - [API — main.py](#api--mainpy)
- [Dataset Schema](#dataset-schema)
- [Dataset Statistics](#dataset-statistics)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Installation](#installation)
- [Deployment](#deployment)
- [Data Quality](#data-quality)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                    │
│                                                                         │
│   pipelineroad.com/directory/type/family-office                        │
│   ~130 family offices: name, location, AUM, asset classes, website     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Stage 1 — Discovery
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               data/pipeline/01_discovered_family_offices.json           │
│               ~130 records: basic fields from listing + detail pages    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Stage 2 — Website Crawl (Crawl4AI)
                               │  Tier 1: Stealth Chromium
                               │  Tier 2: UndetectedAdapter (Cloudflare bypass)
                               │  Tier 3: httpx fallback
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Raw crawled text (in-memory)                        │
│         homepage + up to 6 keyword-ranked subpages per FO              │
│         Structured markers: emails, LinkedIn, socials extracted        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Stage 3 — GPT Extraction (gpt-4o-mini)
                               │  Agent A: company intelligence
                               │  Agent B: people + contacts
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               data/pipeline/02_enriched_family_offices.json             │
│               ~130 records: structured fields merged from               │
│               PipelineRoad data + website-extracted data                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Stage 4 — Contact Discovery (Tavily)
                               │  Tier 1: fill LinkedIn/email gaps
                               │  Tier 2: find contacts from named team
                               │  Tier 3: discover team from scratch
                               │  Email: pattern inference + MX verify
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               data/pipeline/03_contacts_enriched.json                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Stage 4.5 — Enrichment Boost
                               │  MX verification, activity search,
                               │  dedup, placeholder cleanup, country fix
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               data/pipeline/03_contacts_enriched.json (overwritten)     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Stage 5 — Quality Scoring + Export
                               │  5-dimension score (0-100)
                               │  Top-50 selection
                               │  Map to 30-column schema
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│   data/pipeline/04_scored.json       (all FOs, with scores)             │
│   data/pipeline/05_top50.json        (top 50, export schema)            │
│   data/processed/family_office_dataset.csv                              │
│   data/processed/family_office_dataset.xlsx  (formatted, colour-coded) │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  Stage 6 — Embedding + Indexing
                               │  text-embedding-3-small (1536d)
                               │  batch embed 50 records
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               Qdrant Cloud — family_offices collection                  │
│               50 points: 1536d cosine vector + full record payload      │
│               Payload indexes: entity_type, country, state,             │
│               sectors (text), confidence_score, completeness_score      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                 │
              ▼  RAG query                      ▼  direct search
┌─────────────────────────────┐   ┌─────────────────────────────────────┐
│  POST /api/query            │   │  GET /api/search?q=...              │
│  embed question             │   │  embed query → cosine search        │
│  → cosine search (top_k=15) │   │  returns records only (no LLM)      │
│  → format context           │   └─────────────────────────────────────┘
│  → GPT-4o-mini answer       │
│  → answer + records JSON    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      React SPA (frontend/build/)                        │
│                                                                         │
│   ┌────────────────────────┐    ┌────────────────────────────────────┐ │
│   │     Chat Interface     │    │         Explorer Page              │ │
│   │  Natural language Q&A  │    │  Full record table, click-to-view  │ │
│   │  AI answer + citations │    │  all 30 fields per FO              │ │
│   └────────────────────────┘    └────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Stages

```
Stage 1   run_discovery.py          → 01_discovered_family_offices.json
Stage 2/3 run_enrichment.py         → 02_enriched_family_offices.json
Stage 4   run_contact_search.py     → 03_contacts_enriched.json
Stage 4.5 run_enrichment_boost.py   → 03_contacts_enriched.json (overwritten)
                                      + re-runs scoring + XLSX/CSV export
Stage 5   run_scoring.py            → 04_scored.json
                                      05_top50.json
                                      data/processed/XLSX + CSV
Stage 6   run_indexing.py           → Qdrant Cloud
```

All stages read the previous stage's JSON from `data/pipeline/` and write to the next file. Every stage is **resumable** — re-running checks which records are already processed.

---

## File Structure

```
fo-intelligence/
│
├── config/
│   ├── settings.py          # ★ Central env config — all API keys, paths, model names,
│   │                        #   rate limits, target record count. Load-once via dotenv.
│   ├── schema.py            # ★ Pydantic model (FamilyOfficeRecord, 30 fields) + enums
│   │                        #   (EntityType, UrlQuality, EmailConfidence) + COLUMN_ORDER
│   └── prompts.py           # RAG prompt templates: system prompt + query prompt
│
├── src/
│   ├── discovery/
│   │   └── pipelineroad_scraper.py   # ★ Stage 1. Listing page → detail pages → JSON.
│   │                                 #   Regex parsing of concatenated text blocks.
│   │                                 #   Greedy asset-class extraction (longest-first).
│   │                                 #   Resumable: skips already-crawled slugs.
│   │
│   ├── enrichment/
│   │   ├── website_crawler.py        # ★ Stage 2. Crawl4AI two-pass async crawler.
│   │   │                             #   Pass 1: homepage → collect all internal links.
│   │   │                             #   Pass 2: keyword-score links → crawl top 6 subpages.
│   │   │                             #   Tier 1: stealth Chromium (playwright-stealth).
│   │   │                             #   Tier 2: UndetectedAdapter (Cloudflare/DataDome).
│   │   │                             #   Tier 3: httpx plain-HTTP fallback.
│   │   │                             #   Extracts structured markers from all <a href> links.
│   │   │
│   │   ├── gpt_extractor.py          # ★ Stage 3. Two GPT-4o-mini agents.
│   │   │                             #   Agent A: description, thesis, sectors, AUM, activity.
│   │   │                             #   Agent B: team members, best contacts, emails.
│   │   │                             #   Merges with Stage 1 data (website wins on AUM if newer).
│   │   │                             #   Parses structured markers from crawler output.
│   │   │
│   │   ├── google_contact_search.py  # ★ Stage 4. Tavily Search contact enrichment.
│   │   │                             #   Three tiers by existing contact completeness.
│   │   │                             #   Email: direct match → pattern detect → Tavily → MX infer.
│   │   │                             #   LinkedIn: site:linkedin.com/in "name" "company" search.
│   │   │                             #   Title scoring: CIO=10, MD=9, Partner=8, ...
│   │   │
│   │   └── enrichment_boost.py       # Stage 4.5. Six post-processing boosts.
│   │                                 #   1. MX verification (Medium→High email confidence).
│   │                                 #   2. Tavily recent activity search.
│   │                                 #   3. Tavily email discovery for LinkedIn-only contacts.
│   │                                 #   4. Deduplication (known + exact-name duplicates).
│   │                                 #   5. Placeholder cleanup + malformed email removal.
│   │                                 #   6. Country mapping (50 city → country mappings).
│   │
│   ├── validation/
│   │   ├── fo_scorer.py      # ★ Stage 5. 5-dimension quality scorer (0-100).
│   │   │                     #   + Top-50 selection + 30-column schema mapping.
│   │   │                     #   + Best-contact selection algorithm (rank by signals).
│   │   │
│   │   └── validator.py      # XLSX/CSV exporter with professional formatting.
│   │                         #   Verdana 12pt bold headers, Garamond 11pt data.
│   │                         #   4 tier-based header fill colours.
│   │                         #   Conditional fills: entity type, URL quality, score, email confidence.
│   │                         #   Formula injection protection (_neutralize_formula).
│   │                         #   Frozen panes, auto-filters, per-column width tuning.
│   │
│   ├── rag/
│   │   ├── embedder.py       # OpenAI text-embedding-3-small (1536d) wrapper.
│   │   │                     #   record_to_text(): converts 30-field record to prose.
│   │   │                     #   Batched embeddings (20 per call).
│   │   │
│   │   ├── indexer.py        # Qdrant collection setup + upsert.
│   │   │                     #   Payload indexes: entity_type, country, state, sectors,
│   │   │                     #   confidence_score, completeness_score.
│   │   │
│   │   ├── retriever.py      # Semantic search + structured filter builder.
│   │   │                     #   Supports qdrant-client v1 (.search) and v2 (.query_points).
│   │   │                     #   Filters: entity_type, country, state, min_confidence, min_completeness.
│   │   │
│   │   └── generator.py      # Full RAG pipeline: embed → retrieve → GPT-4o-mini → answer.
│   │                         #   Dynamic max_tokens: 300 + records×200, clamped 600-4096.
│   │
│   └── api/
│       └── main.py           # ★ FastAPI app. 6 endpoints + static React serving.
│
├── frontend/
│   └── build/
│       ├── index.html        # Chat interface (React SPA, pre-built, no build step)
│       └── explore.html      # Dataset Explorer (full record table + detail view)
│
├── data/
│   ├── pipeline/
│   │   └── 01_discovered_family_offices.json   # Stage 1 output (committed)
│   │       (02, 03, 04, 05 regenerated on-the-fly — NOT committed)
│   │
│   └── processed/
│       ├── family_office_dataset.csv
│       ├── family_office_dataset.xlsx
│       └── dataset_stats.json
│
├── run_discovery.py          # Stage 1 runner
├── run_enrichment.py         # Stage 2+3 runner
├── run_contact_search.py     # Stage 4 runner
├── run_enrichment_boost.py   # Stage 4.5 runner (also re-runs scoring + export)
├── run_scoring.py            # Stage 5 runner
├── run_indexing.py           # Stage 6 runner
├── tag_enriched_sources.py   # Utility: tag 02_enriched.json with provenance metadata
├── test_rag.py               # Smoke test: 5 sample queries against Qdrant
├── requirements.txt
├── Dockerfile                # python:3.11-slim, port 10000
├── render.yaml               # Render free-tier Docker deployment config
└── .env.example
```

---

## Module Deep Dive

### Stage 1 — `pipelineroad_scraper.py`

Scrapes the PipelineRoad LP directory for all ~130 family offices in two passes.

**Pass 1 — Listing page:**
```
https://pipelineroad.com/directory/type/family-office
→ find all <a href="/directory/{slug}"> anchors (regex: ^/directory/[a-z0-9...]+$)
→ get_text() → parse with _parse_listing_text()
```

The listing text is a concatenated string like:
```
"C Cascade Investment Family Office · Kirkland, WA AUM $70B Private EquityReal Estate +1"
```

Parsing steps:
1. Split on `·` separator → name part + rest
2. Strip leading avatar initial (`"C Cascade..."` → `"Cascade..."`)
3. Regex-extract AUM `$NNB/M/T`
4. Greedy-extract asset classes (sorted longest-first to prevent partial matches)

**Pass 2 — Detail pages:**
```
https://pipelineroad.com/directory/{slug}
→ extract: website URL (↗ icon links), description (meta tag),
           AUM + date, alternatives allocation, headquarters, investment strategy
```

Resumable: records with `crawl_status == "Discovered"` are skipped. Incremental save every 10 records.

**Output fields from Stage 1:**
```
name, slug, type, location, aum, asset_classes, detail_url, website,
description, aum_date, alternatives_allocation, headquarters,
investment_strategy, source="PipelineRoad", discovery_confidence="High"
```

---

### Stage 2 — `website_crawler.py`

Async Crawl4AI crawler. Handles JS-rendered sites, anti-bot protection, and icon-embedded links.

**Two-pass architecture per FO:**
```
Pass 1: Crawl homepage
  → collect ALL <a href> (internal + external)
  → extract mailto: links, LinkedIn /in/ profiles, LinkedIn /company/ pages
  → score each internal link by keyword relevance

Pass 2: Crawl top-scored subpages (max 6)
  → keywords: team, people, leadership, about, contact, invest,
    portfolio, strategy, news, press, blog, insights, press...
  → score: URL path match (+2), link text match (+1) per keyword
  → crawl top N by score, skip already-visited
```

**Three-tier anti-detection fallback:**

| Tier | Method | Use Case |
|------|--------|----------|
| 1 | Crawl4AI + playwright-stealth | Most sites — randomized mouse moves, navigator override, magic mode |
| 2 | UndetectedAdapter | Cloudflare, DataDome, Akamai CDP blocking — deep fingerprint patches |
| 3 | httpx plain-HTTP | Sites that serve full HTML to non-browser clients |

**Structured marker extraction:**
After crawling, all collected `<a href>` links are scanned for:
- `mailto:` → email addresses (including icon-embedded, invisible-text links)
- `linkedin.com/in/` → personal LinkedIn profiles
- `linkedin.com/company/` → corporate LinkedIn pages
- Twitter/X, Facebook, Instagram → social links

These are embedded in the output text as structured blocks:
```
=== EXTRACTED_EMAILS ===
info@example.com
john.doe@example.com

=== CORPORATE_LINKEDIN ===
https://linkedin.com/company/example-fo

=== LINKEDIN_PROFILES ===
https://linkedin.com/in/jane-smith
```

GPT and the contact enrichment pipeline parse these markers separately from the prose text.

---

### Stage 3 — `gpt_extractor.py`

Two parallel GPT-4o-mini agents, each seeing the first 6,000 characters of crawled text.

**Agent A — Company Intelligence:**
```
Extracts → description, investment_thesis, sectors[], geographic_focus[],
           founded_year, firm_type (SFO/MFO/Hybrid/Unknown), min_investment,
           notable_holdings[], aum, aum_year, recent_activity{title,date,url,summary}

Response format: JSON object (response_format={"type": "json_object"})
Temperature: 0.1 (deterministic)
Max tokens: 2000
```

**Agent B — People & Contacts:**
```
Extracts → team_members[{name, title, email, linkedin_url, is_key_contact}],
           best_contacts[{name, title, reason}],
           primary_email, phone, address

is_key_contact=True for: CEO, CIO, Partner, MD, Principal, Head of
best_contacts: top 2-3 for investment outreach (not admin/IR)
```

**Merge logic:**
- Stage 1 data is the base — website data only overwrites where it has a value
- AUM: keep more recent year (website_year >= PipelineRoad year → website wins)
- Structured markers (from crawler) parsed separately and merged

---

### Stage 4 — `google_contact_search.py`

Tavily Search-powered contact enrichment. Three tiers based on what Stage 3 found.

**Tier classification:**
```
Tier 1 — Has team members with ≥1 contact (email or LinkedIn): fill gaps
Tier 2 — Has named team members but no contacts: find both
Tier 3 — No real team members at all: discover people + contacts from scratch
```

**Placeholder filtering** (prevents enriching GPT hallucinations):
Names like "Full Name", "John Doe", "Leadership Team", single-word entries, and company-name-as-person are filtered out before enrichment.

**LinkedIn search:**
```python
# Primary (quoted company name)
query = f'site:linkedin.com/in "{name}" "{clean_company}"'

# Fallback (unquoted)
query = f'site:linkedin.com/in "{name}" {clean_company}'

# Tier 3 team discovery
query = f'site:linkedin.com/in "{company}" (CIO OR "Managing Director" OR Partner OR CEO)'
```

Title relevance scoring:
```
CIO, Chief Investment Officer → 10
Managing Director, Managing Partner → 9
Head of Investments, General Partner, Partner → 8-9
CEO, President → 7
CFO, COO, Principal → 6
VP, Director → 4-5
Analyst, Associate → 1
```

**Email discovery — 4-step strategy:**
```
1. Direct match: scan existing extracted_emails for first+last pattern match
2. Pattern detection: if domain has known emails, detect format
   (first.last / f.last / firstlast / flast) → apply to new person
3. Tavily search: '"first last" "@domain"' → scan snippets for pattern match
4. MX inference: if domain has MX records + known pattern → infer with Low confidence
```

**Email confidence levels:**
- `High` — found in search snippet OR pattern-inferred + MX verified
- `Medium` — pattern-inferred from domain structure
- `Low` — inferred with no MX confirmation
- `Not Found` — no email located

---

### Stage 4.5 — `enrichment_boost.py`

Six post-processing boosts applied after Stage 4, before scoring.

**1. MX Verification (DNS, free):**
For every team member email, resolve the domain's MX records. `Medium` confidence upgraded to `High` if MX passes; downgraded to `Low` if MX fails. Results cached per domain.

**2. Recent Activity Search (Tavily, up to 60 queries):**
For FOs without `recent_activity`, searches `"{name}" family office investment news 2024 2025`. Picks the most relevant result (must mention FO name or key word). Extracts date using 4 regex patterns.

**3. Email Discovery (Tavily, up to 40 queries):**
Finds emails for team members who have LinkedIn but no email. First tries domain-based pattern inference, then Tavily search.

**4. Deduplication:**
Known hard-coded duplicates (e.g. "Ken Griffin Family Office" → keep "Citadel LLC"). Exact-name case-insensitive deduplication. Trailing "Family Office" suffix stripped before comparison.

**5. Placeholder Cleanup:**
Removes team members matching placeholder names, single-word names, or company-as-person patterns. Removes structurally malformed emails (stray parentheses, spaces, invalid format).

**6. Country Mapping:**
50 city-to-country mappings (London → UK, Zurich → Switzerland, Dubai → UAE, etc.) + country keyword scan on the headquarters string. Prevents non-US FOs from defaulting to "United States".

---

### Stage 5 — `fo_scorer.py` + `validator.py`

**Quality Scorer (0-100)**

Five analytical dimensions — no additional API queries:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Contact Quality | 30 pts | Email confidence (0-15) + LinkedIn presence (0-10) + title seniority (0-5) |
| Entity Intelligence | 25 pts | Website crawled (0-8) + investment strategy (0-5) + AUM (0-4) + HQ (0-3) + founded (0-2) + description (0-3) |
| Team Discovery | 20 pts | Team count (0-6) + LinkedIn count (0-6) + email count (0-5) + discovery source tier (0-3) |
| Corporate Presence | 15 pts | Company LinkedIn (0-6) + extracted corporate email (0-4) + social links (0-3) + LinkedIn profiles (0-2) |
| Data Completeness | 10 pts | Mappable fields / 30 × 10 |

**Best contact selection** (for Tier 2 export):
Team members ranked by: `(has_email + has_linkedin, has_email, is_senior, has_linkedin)` descending. Placeholders filtered before ranking.

**Export schema mapping (30 columns):**
Enriched internal JSON → canonical 30-column export schema. Name normalization strips trailing " Family Office" suffix. Entity type normalization handles "multi"/"mfo"/"single"/"sfo" variants. AUM source defaults to "PipelineRoad". Country: resolved country from boost > explicit 3rd part > US-state-aware defaulting.

**XLSX Formatting (`validator.py`):**
```
Headers: Verdana 12pt bold, white text
  Tier 1 → #1B3A5C (dark navy)
  Tier 2 → #2E5984 (medium navy)
  Tier 3 → #3D7AB5 (lighter blue)
  Tier 4 → #4A8CC7 (lightest blue)

Data rows: Garamond 11pt
  family_office_name: bold, #1B3A5C
  Alternating row fills: #EAF0F7 / #FFFFFF
  Medium border: #B4C6E0

Conditional fills:
  entity_type: SFO=green, MFO=blue, Hybrid=yellow
  url_quality: Highest=green, Medium=yellow, Lower/Medium-Low=red, Not Found=grey
  score columns: ≥70=green bold, ≥40=yellow, <40=red
  email_confidence: High/Verified=green, Medium=yellow, Low=red, Not Found=grey

Formula injection protection: strings starting with =,+,-,@,\t prefixed with '
Frozen panes at B2, auto-filter on all columns
```

---

### Stage 6 — RAG Stack

Four modules working together:

**`embedder.py` — Record-to-vector conversion:**
```python
def record_to_text(record):
    # Converts 30-field record to a natural-language prose document:
    "Family Office: Wafra\nType: Single Family Office\nAUM: $30 billion\n
     Investment Thesis: ...\nInvesting Sectors: ...\nLocation: New York, US\n
     Key Contact: Abdulaziz Al-Mutairi (Chief Executive Officer)\n
     Recent Activity: ...\nCorporate Email: info@wafra.com\n..."

# Batched embedding: 20 records per OpenAI API call
# Model: text-embedding-3-small (1536 dimensions, cosine similarity)
```

**`indexer.py` — Qdrant collection setup:**
```python
# Collection: family_offices
# Vectors: 1536d cosine
# Payload indexes for filtered search:
#   entity_type, hq_country, hq_state → KEYWORD
#   investing_sectors → TEXT (token match)
#   confidence_score, data_completeness_score → FLOAT (range queries)
```

**`retriever.py` — Semantic search + structured filters:**
```python
# API compatibility: supports qdrant-client v1 (.search) and v2 (.query_points)
# Filter builder converts dict → Qdrant Filter with FieldCondition
# Supported filters: entity_type, hq_country, hq_state, min_confidence, min_completeness
```

**`generator.py` — RAG pipeline:**
```python
query_rag(question, top_k=15, filters=None):
    1. embed(question) → 1536d vector
    2. qdrant.search(vector, limit=top_k) → records
    3. format_context(records) → compact text (name, AUM, sectors, location, thesis, activity)
    4. gpt-4o-mini(system_prompt, context, question) → natural language answer
    5. return {answer, records, query}

# Dynamic max_tokens: 300 + (records × 200), clamped [600, 4096]
# Temperature: 0.3 (allows some creative phrasing while staying factual)
```

RAG system prompt instructs the model to:
- Base answers ONLY on retrieved records
- Use compact format: name, AUM, type, location, "Why Them" (2-3 lines per FO)
- Include ALL matching records — do not skip any
- End with a "Key Takeaway" one-liner
- Never list full field-by-field details (Explorer shows those)

---

### API — `main.py`

FastAPI application serving both the REST API and the pre-built React frontend.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/query` | Full RAG query — embed + retrieve + GPT answer |
| GET | `/api/search?q=&top_k=` | Semantic search — records only, no LLM generation |
| GET | `/api/records?limit=&entity_type=&country=` | List records with optional filters |
| GET | `/api/records/{id}` | Get single record by Qdrant point ID |
| GET | `/api/stats` | Dataset stats (total, avg scores, entity_type dist, country dist) |
| GET | `/{path}` | Serve React SPA (catch-all, returns index.html) |

**Frontend serving:**
```python
FRONTEND_DIR = project_root / "frontend" / "build"
# /static/* → StaticFiles mount (JS, CSS, images)
# /* → FileResponse(index.html) for client-side routing
```

---

## Dataset Schema

30 columns across 4 tiers:

```
Tier 1 — Entity Core (18 columns)
  family_office_name    Official entity name (trailing "Family Office" stripped)
  entity_type           Single Family Office | Multi Family Office | Hybrid | Unknown
  description           2-3 sentence company summary (website-sourced)
  year_founded          Year established
  aum_estimated         Assets Under Management (e.g. "$30 billion", "$500M")
  aum_source            Data source + year reference
  investment_thesis     Core investment philosophy (1-2 sentences)
  investing_sectors     Comma-separated sector list
  website_url           Primary website (https://)
  url_quality           Highest | Medium | Medium-Low | Lower | Not Found
  corporate_linkedin    Company LinkedIn page URL
  linkedin_source       How corporate LinkedIn was found
  corporate_email       General contact email (info@, contact@, office@…)
  corp_email_source     How corporate email was found
  other_socials         Twitter, Facebook, Instagram URLs (pipe-separated)
  hq_city               Headquarters city
  hq_state              State, province, or region
  hq_country            Country (explicit or resolved via city/keyword mapping)

Tier 2 — Principal Intelligence (6 columns)
  contact_name          Best decision-maker name
  contact_title         Their title/role
  contact_linkedin      Personal LinkedIn URL
  contact_email         Email address
  email_confidence      Verified | High | Medium | Low | Not Found
  email_source          How email was obtained/verified

Tier 3 — Entity Signals (4 columns)
  recent_activity       Latest news or press headline
  activity_date         Date of activity (regex-extracted)
  activity_source_url   Source link for activity
  key_investments       Notable portfolio companies or deals (comma-separated)

Tier 4 — Data Quality (2 columns)
  data_completeness_score   % of non-null columns (0-100, recalculated at export)
  confidence_score          Analytical quality score (0-100) from fo_scorer.py
```

---

## Dataset Statistics

Current committed dataset (`data/processed/dataset_stats.json`):

| Metric | Value |
|--------|-------|
| Total records | 50 |
| Average completeness score | 85.1% |
| Average confidence score | 86.7% |
| Records with website | 50 (100%) |
| Records with contact name | 50 (100%) |
| Records with contact email | 50 (100%) |
| Records with contact LinkedIn | 50 (100%) |
| Records with AUM data | 48 (96%) |
| Records with recent activity | 45 (90%) |
| Entity types | 35 SFO, 4 MFO, 1 Hybrid, 10 Unknown |
| Email confidence split | 24 High, 26 Medium |
| URL quality | All 50 = "Highest" (all crawled successfully) |

**Field coverage highlights:**
- 100% coverage: name, description, thesis, sectors, website, URL quality, corporate LinkedIn, city, state, contact name, title, LinkedIn, email, email confidence, completeness, confidence
- 96% AUM, 94% country, 90% recent activity, 80% entity type, 62% year founded

---

## API Reference

### POST `/api/query`

Full RAG pipeline. Embeds query, retrieves matching records, generates GPT answer.

**Request:**
```json
{
  "question": "Which family offices invest in AI and technology?",
  "top_k": 5,
  "filters": {
    "entity_type": "Single Family Office",
    "hq_country": "United States",
    "min_confidence": 60
  }
}
```

**Response:**
```json
{
  "answer": "Here are the top family offices investing in AI...\n\n### 1. **Wafra**\n...",
  "records": [ { ...30 fields + _similarity_score... }, ... ],
  "query": "Which family offices invest in AI and technology?"
}
```

**Supported filters:**

| Filter key | Type | Description |
|------------|------|-------------|
| `entity_type` | string | "Single Family Office", "Multi Family Office", "Hybrid" |
| `hq_country` | string | Country name (exact match) |
| `hq_state` | string | State/province (exact match) |
| `min_confidence` | float | Minimum confidence_score (0-100) |
| `min_completeness` | float | Minimum data_completeness_score (0-100) |

### GET `/api/search`

Semantic search without LLM generation — faster and cheaper.

```
GET /api/search?q=technology+investors+New+York&top_k=10
```

**Response:**
```json
{
  "query": "technology investors New York",
  "total": 10,
  "records": [ { ...30 fields + _similarity_score... }, ... ]
}
```

### GET `/api/records`

List records with optional simple filters.

```
GET /api/records?limit=50&entity_type=Single Family Office&country=United States
```

### GET `/api/stats`

Dataset summary statistics for the frontend dashboard.

```json
{
  "total_records": 50,
  "avg_completeness": 85.1,
  "avg_confidence": 86.7,
  "entity_types": { "Single Family Office": 35, "Multi Family Office": 4, ... },
  "countries": { "United States": 38, "United Kingdom": 5, ... }
}
```

**cURL example:**
```bash
curl -X POST https://fo-intelligence.onrender.com/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Family offices with real estate focus", "top_k": 5}'
```

**Python example:**
```python
import requests

resp = requests.post(
    "http://localhost:8000/api/query",
    json={
        "question": "Which SFOs invest in healthcare and biotech?",
        "top_k": 5,
        "filters": {"entity_type": "Single Family Office"}
    }
)
result = resp.json()
print(result["answer"])
for r in result["records"]:
    print(r["family_office_name"], r["_similarity_score"])
```

---

## Configuration

All configuration is through environment variables. Copy `.env.example` to `.env` and fill in:

```bash
# Required
OPENAI_API_KEY=sk-proj-...          # GPT-4o-mini + text-embedding-3-small
QDRANT_URL=https://...qdrant.io     # Qdrant Cloud cluster URL
QDRANT_API_KEY=...                  # Qdrant API key

# Required for pipeline (not needed for API-only mode)
TAVILY_API_KEY=...                  # Tavily Search API (Stage 4 contact discovery)

# Optional pipeline keys
BRAVE_API_KEY=...                   # Legacy (kept for reference, Tavily is primary)
OPENROUTER_API_KEY=...              # For FO classification (Claude Haiku 4.5 default)
OPENROUTER_MODEL=anthropic/claude-haiku-4.5

# Optional: override defaults
COLLECTION_NAME=family_offices      # Qdrant collection name
EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL=gpt-4o-mini
TOP_K=15                            # Default retrieval count for RAG

# Pipeline constants (in settings.py)
MAX_CANDIDATES=150                  # Max FOs from discovery
TARGET_RECORDS=50                   # Final dataset size
REQUEST_DELAY=1.0                   # Seconds between web requests
```

---

## Installation

### Prerequisites

| Requirement | Notes |
|------------|-------|
| Python 3.11+ | 3.11 recommended (used in Docker) |
| OpenAI API key | GPT-4o-mini + text-embedding-3-small |
| Qdrant Cloud account | Free tier works (50 records is tiny) |
| Tavily API key | For contact discovery (Stage 4 only) |

### Quick Start — API only (no pipeline)

The final dataset is committed. You can index it and serve the API without running any pipeline stages.

```bash
git clone https://github.com/codera647/fo-intelligence.git
cd fo-intelligence

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your OpenAI + Qdrant keys

# Index the committed dataset into Qdrant
python run_indexing.py

# Serve the API + frontend
uvicorn src.api.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

Test the RAG stack:
```bash
python test_rag.py
```

### Full Pipeline from Scratch

```bash
# Additional dependencies for Stage 2 (Crawl4AI)
pip install crawl4ai
crawl4ai-setup     # installs Playwright browsers + Chromium
pip install dnspython   # for MX verification in Stage 4

# Run pipeline stages in order
python run_discovery.py         # Stage 1 — ~5 min (130 detail pages, 1s delay each)
python run_enrichment.py        # Stage 2/3 — ~2-3 hours (crawl + GPT per FO)
python run_contact_search.py    # Stage 4 — ~1 hour (Tavily queries, rate-limited)
python run_enrichment_boost.py  # Stage 4.5 — ~30 min (MX + Tavily boosts + re-export)
python run_scoring.py           # Stage 5 — <1 min (analytical, no API calls)
python run_indexing.py          # Stage 6 — ~2 min (50 embeddings + Qdrant upsert)
```

Stages 2-5 are resumable: re-running picks up where the previous run left off.

---

## Deployment

### Render (current)

```yaml
# render.yaml
services:
  - type: web
    name: fo-intelligence
    runtime: docker
    plan: free
    envVars:
      - key: OPENAI_API_KEY
      - key: QDRANT_URL
      - key: QDRANT_API_KEY
      - key: COLLECTION_NAME
        value: family_offices
      - key: LLM_MODEL
        value: gpt-4o-mini
      - key: TOP_K
        value: "5"
```

Deploy: push to GitHub → Render auto-builds Docker image → deploys on port 10000.

### Docker

```bash
docker build -t fo-intelligence .
docker run -p 10000:10000 \
  -e OPENAI_API_KEY=sk-... \
  -e QDRANT_URL=https://... \
  -e QDRANT_API_KEY=... \
  fo-intelligence
```

---

## Data Quality

Two per-record scores measure different things:

**`data_completeness_score` (0-100)**
The percentage of the 30 schema columns that are non-null. Recalculated at export by `validator._clean_record()`. "Not Found", "N/A", and empty strings count as null.

**`confidence_score` (0-100)**
An analytical quality/richness score from `fo_scorer.py` based on five signal dimensions: contact completeness, entity intelligence, team discovery, corporate presence, and field coverage. It measures *how much structured data was assembled*, not independent verification.

**`email_confidence`** values and what they mean:

| Value | Meaning |
|-------|---------|
| Verified | Address confirmed directly (Hunter.io / Apollo — not currently implemented) |
| High | Pattern-inferred AND domain passed MX verification |
| Medium | Pattern-inferred from corporate domain, not MX-checked |
| Low | Generic address scraped from website, or MX check failed |
| Not Found | No email located |

**Known data limitations:**
- Contact emails are domain-verified, not individually confirmed
- ~20 records have Unknown entity type (could not be determined from available data)
- Discovery is single-source (PipelineRoad only)
- Recent activity pulled from Tavily search snippets — dates may be approximate

---

## Roadmap

- [ ] Hunter.io / Apollo integration for individual email verification
- [ ] LinkedIn scraping agent for genuine principal intelligence
- [ ] Additional discovery sources (DealCloud, Preqin, SEC EDGAR family office filings)
- [ ] Multi-agent consensus verification across sources
- [ ] Scheduled re-crawling for fresh activity signals
- [ ] Entity type classification for the ~10 Unknown records
- [ ] Expand to 200-record dataset (current pipeline handles it — just increase `TARGET_RECORDS`)
- [ ] Export to Airtable / Notion / HubSpot via API connectors

---

## Acknowledgements

| Project | Use |
|---------|-----|
| [PipelineRoad](https://pipelineroad.com) | Family office directory (Stage 1 source) |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | JS-rendering headless crawling + anti-detection |
| [OpenAI GPT-4o-mini](https://openai.com) | Extraction agents + RAG generation |
| [OpenAI text-embedding-3-small](https://openai.com) | 1536d semantic embeddings |
| [Qdrant](https://qdrant.tech) | Vector database with payload filtering |
| [Tavily Search](https://tavily.com) | Programmatic web search for contacts |
| [FastAPI](https://fastapi.tiangolo.com) | REST API + static file serving |
| [LangChain](https://langchain.com) | RAG pipeline orchestration |
| [Render](https://render.com) | Free-tier Docker deployment |

---

<div align="center">

Built by [Abdul Moiz](https://github.com/codera647)

</div>
