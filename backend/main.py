"""
main.py — FastAPI backend for RAG demo
Run: uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from auth import verify_jwt_token
from rag import (
    RAGEngine,
    MODELS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
)

UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="RAG Demo API")

# Allow all origins in dev — tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Engine singleton (one per process) ----------

_engine: Optional[RAGEngine] = None


def get_engine() -> RAGEngine:
    global _engine
    if _engine is None:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

        if not openai_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY ikke satt.")

        _engine = RAGEngine(
            openai_api_key=openai_key,
            anthropic_api_key=anthropic_key or None,
        )
    return _engine


def ensure_valid_model(model: str) -> None:
    if model not in MODELS:
        raise HTTPException(status_code=400, detail=f"Ugyldig modell: {model}")


def attach_urls_to_points(points: list[dict]) -> list[dict]:
    enriched = []

    for p in points:
        item = dict(p)
        src = item.get("source", "")

        if src and src != "Manuell tekst" and (UPLOADS_DIR / src).exists():
            page = item.get("page")
            item["url"] = f"/files/{quote(src)}" + (f"#page={page}" if page else "")
        else:
            item["url"] = None

        enriched.append(item)

    return enriched


# ---------- Routes ----------

@app.get("/me")
def me(user=Depends(verify_jwt_token)):
    return {
        "sub": user.get("sub"),
        "email": user.get("email"),
        "name": user.get("name"),
    }


@app.get("/files/{filename}")
def get_file(filename: str, user=Depends(verify_jwt_token)):
    file_path = UPLOADS_DIR / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Fil ikke funnet.")

    media_type = None
    if file_path.suffix.lower() == ".pdf":
        media_type = "application/pdf"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )


@app.get("/models")
def list_models(user=Depends(verify_jwt_token)):
    return [
        {"id": k, "label": v["label"], "provider": v["provider"]}
        for k, v in MODELS.items()
    ]


@app.post("/index")
async def index_documents(
    files: List[UploadFile] = File(default=[]),
    manual_text: str = Form(default=""),
    chunk_size: int = Form(default=DEFAULT_CHUNK_SIZE),
    overlap: int = Form(default=DEFAULT_OVERLAP),
    user=Depends(verify_jwt_token),
):
    engine = get_engine()
    all_chunks = []

    for f in files:
        data = await f.read()
        dest = UPLOADS_DIR / f.filename
        dest.write_bytes(data)

        try:
            segments = engine.extract_text_from_bytes(data, f.filename)
            for seg in segments:
                chunks = engine.chunk_text(
                    seg["text"],
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                for c in chunks:
                    all_chunks.append(
                        {
                            "source": f.filename,
                            "text": c,
                            "page": seg["page"],
                        }
                    )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if manual_text.strip():
        for c in engine.chunk_text(
            manual_text,
            chunk_size=chunk_size,
            overlap=overlap,
        ):
            all_chunks.append(
                {
                    "source": "Manuell tekst",
                    "text": c,
                    "page": None,
                }
            )

    if not all_chunks:
        raise HTTPException(status_code=400, detail="Ingen tekst å indeksere.")

    n = engine.index_chunks(all_chunks, chunk_size=chunk_size, overlap=overlap)
    return {
        "indexed": n,
        "chunk_size": chunk_size,
        "overlap": overlap,
    }


class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=8, ge=1, le=20)
    min_score: float = Field(default=0.40, ge=0.0, le=1.0)
    score_threshold: float = Field(default=0.20, ge=0.0, le=1.0)


@app.post("/search")
def search(req: SearchRequest, user=Depends(verify_jwt_token)):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Spørsmål kan ikke være tomt.")

    engine = get_engine()
    points = engine.search(
        req.query,
        limit=req.k,
        min_score=req.min_score,
    )

    strong = [p for p in points if p["score"] >= req.score_threshold]
    weak_count = len(points) - len(strong)
    strong = attach_urls_to_points(strong)

    return {
        "points": strong,
        "filtered_count": weak_count,
        "returned_count": len(strong),
    }


class RagRequest(BaseModel):
    query: str
    points: list
    model: str


@app.post("/rag")
def rag(req: RagRequest, user=Depends(verify_jwt_token)):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Spørsmål kan ikke være tomt.")
    if not req.points:
        raise HTTPException(status_code=400, detail="Ingen punkter å basere svar på.")

    ensure_valid_model(req.model)
    engine = get_engine()

    result = engine.rag_answer(req.query, req.points, req.model)

    # Legg ved alle innsendte punkter med URL slik at frontend kan vise kildene
    source_map = {p["chunk_id"]: p for p in attach_urls_to_points(req.points)}
    used_points = [source_map[cid] for cid in result.get("used_chunks", []) if cid in source_map]

    return {
        "answer": result.get("answer", ""),
        "used_chunks": result.get("used_chunks", []),
        "notes": result.get("notes", ""),
        "sources": used_points,
    }


@app.post("/rag/stream")
def rag_stream(req: RagRequest, user=Depends(verify_jwt_token)):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Spørsmål kan ikke være tomt.")
    if not req.points:
        raise HTTPException(status_code=400, detail="Ingen punkter å basere svar på.")

    ensure_valid_model(req.model)
    engine = get_engine()

    source_map = {p["chunk_id"]: p for p in attach_urls_to_points(req.points)}

    def generate():
        for event in engine.stream_answer(req.query, req.points, req.model):
            if event.get("type") == "done":
                used_chunks = event.get("used_chunks", [])
                event["sources"] = [source_map[cid] for cid in used_chunks if cid in source_map]

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class SummarizeRequest(BaseModel):
    model: str


@app.post("/summarize/{filename}")
def summarize(filename: str, req: SummarizeRequest, user=Depends(verify_jwt_token)):
    ensure_valid_model(req.model)

    engine = get_engine()
    summary = engine.summarize_document(filename, req.model)
    return {"summary": summary}


@app.delete("/collection")
def delete_collection(user=Depends(verify_jwt_token)):
    engine = get_engine()

    try:
        engine.delete_collection()
    except Exception as e:
        print(f"[WARN] Klarte ikke tømme vector DB: {e}")

    for f in UPLOADS_DIR.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except Exception as e:
                print(f"[WARN] Klarte ikke slette fil {f.name}: {e}")

    return {"deleted": True}


@app.get("/documents")
def list_documents(user=Depends(verify_jwt_token)):
    files = sorted(f.name for f in UPLOADS_DIR.iterdir() if f.is_file())
    return {"files": files}


@app.delete("/documents/{filename}")
def delete_document(filename: str, user=Depends(verify_jwt_token)):
    engine = get_engine()

    try:
        engine.delete_by_source(filename)
    except Exception as e:
        print(f"[WARN] Klarte ikke slette fra vector DB: {e}")

    try:
        f = UPLOADS_DIR / filename
        if f.exists():
            f.unlink()
    except Exception as e:
        print(f"[WARN] Klarte ikke slette fil: {e}")
        raise HTTPException(status_code=500, detail="Feil ved sletting av fil")

    return {"deleted": filename}
