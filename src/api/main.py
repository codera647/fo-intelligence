"""FastAPI application — REST API + serves React frontend."""

import os
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ── configure logging before imports ──────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── add project root to path ──────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.rag.generator import query_rag
from src.rag.retriever import search_family_offices, get_all_records, get_record_by_id

# ── app ───────────────────────────────────────────────────────────
app = FastAPI(
    title="FO Intelligence",
    description="Family Office Intelligence — Micro-RAG Pipeline",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── request/response models ──────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    filters: Optional[dict] = None


class QueryResponse(BaseModel):
    answer: str
    records: list
    query: str


# ── endpoints ─────────────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "FO Intelligence RAG"}


@app.post("/api/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """Main RAG query endpoint — natural language search over FO dataset."""
    try:
        result = query_rag(
            question=request.question,
            top_k=request.top_k,
            filters=request.filters,
        )
        return result
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/records")
async def list_records(
    limit: int = Query(50, ge=1, le=100),
    entity_type: Optional[str] = None,
    country: Optional[str] = None,
):
    """List all FO records with optional filtering."""
    try:
        records = get_all_records()

        # Apply simple filters
        if entity_type:
            records = [r for r in records if r.get("entity_type") == entity_type]
        if country:
            records = [r for r in records if r.get("hq_country", "").lower() == country.lower()]

        return {
            "total": len(records),
            "records": records[:limit],
        }
    except Exception as e:
        logger.error(f"List records failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/records/{record_id}")
async def get_single_record(record_id: int):
    """Get a single FO record by ID."""
    record = get_record_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.get("/api/search")
async def search_endpoint(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
):
    """Quick semantic search (returns records without LLM generation)."""
    try:
        records = search_family_offices(query=q, top_k=top_k)
        return {
            "query": q,
            "total": len(records),
            "records": records,
        }
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def dataset_stats():
    """Return dataset statistics."""
    try:
        records = get_all_records()

        entity_types = {}
        countries = {}
        total_completeness = 0
        total_confidence = 0

        for r in records:
            et = r.get("entity_type", "Unknown")
            entity_types[et] = entity_types.get(et, 0) + 1

            country = r.get("hq_country", "Unknown")
            countries[country] = countries.get(country, 0) + 1

            total_completeness += r.get("data_completeness_score", 0)
            total_confidence += r.get("confidence_score", 0)

        n = len(records) or 1

        return {
            "total_records": len(records),
            "avg_completeness": round(total_completeness / n, 1),
            "avg_confidence": round(total_confidence / n, 1),
            "entity_types": entity_types,
            "countries": countries,
        }
    except Exception as e:
        logger.error(f"Stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Serve React frontend (static build) ──────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "build"

if FRONTEND_DIR.exists():
    # Mount static assets if the directory exists
    static_dir = FRONTEND_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React app for all non-API routes."""
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
