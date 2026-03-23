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
from pydantic import BaseModel

from auth import verify_jwt_token
from rag import RAGEngine, MODELS, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP

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
    return [{"id": k, "label": v["label"], "provider": v["provider"]} for k, v in MODELS.items()]


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
                chunks = engine.chunk_text(seg["text"], chunk_size=chunk_size, overlap=overlap)
                for c in chunks:
                    all_chunks.append({"source": f.filename, "text": c, "page": seg["page"]})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if manual_text.strip():
        for c in engine.chunk_text(manual_text, chunk_size=chunk_size, overlap=overlap):
            all_chunks.append({"source": "Manuell tekst", "text": c, "page": None})

    if not all_chunks:
        raise HTTPException(status_code=400, detail="Ingen tekst å indeksere.")

    n = engine.index_chunks(all_chunks)
    return {"indexed": n}


class SearchRequest(BaseModel):
    query: str
    k: int = 5
    min_score: float = 0.15
    score_threshold: float = 0.15


@app.post("/search")
def search(req: SearchRequest, user=Depends(verify_jwt_token)):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Spørsmål kan ikke være tomt.")
    engine = get_engine()
    points = engine.search(req.query, limit=req.k, min_score=req.min_score)
    strong = [p for p in points if p["score"] >= req.score_threshold]
    weak_count = len(points) - len(strong)

    for p in strong:
        src = p.get("source", "")
        if src and src != "Manuell tekst" and (UPLOADS_DIR / src).exists():
            page = p.get("page")
            p["url"] = f"/files/{quote(src)}" + (f"#page={page}" if page else "")
        else:
            p["url"] = None

    return {"points": strong, "filtered_count": weak_count}


class RagRequest(BaseModel):
    query: str
    points: list
    model: str


@app.post("/rag")
def rag(req: RagRequest, user=Depends(verify_jwt_token)):
    if not req.points:
        raise HTTPException(status_code=400, detail="Ingen punkter å basere svar på.")
    engine = get_engine()
    result = engine.rag_answer(req.query, req.points, req.model)
    return result


@app.post("/rag/stream")
def rag_stream(req: RagRequest, user=Depends(verify_jwt_token)):
    if not req.points:
        raise HTTPException(status_code=400, detail="Ingen punkter å basere svar på.")
    engine = get_engine()

    def generate():
        for event in engine.stream_answer(req.query, req.points, req.model):
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
    engine = get_engine()
    summary = engine.summarize_document(filename, req.model)
    return {"summary": summary}


@app.delete("/collection")
def delete_collection(user=Depends(verify_jwt_token)):
    engine = get_engine()
    engine.delete_collection()
    for f in UPLOADS_DIR.iterdir():
        if f.is_file():
            f.unlink()
    return {"deleted": True}


@app.get("/documents")
def list_documents(user=Depends(verify_jwt_token)):
    files = sorted(f.name for f in UPLOADS_DIR.iterdir() if f.is_file())
    return {"files": files}


@app.delete("/documents/{filename}")
def delete_document(filename: str, user=Depends(verify_jwt_token)):
    engine = get_engine()
    engine.delete_by_source(filename)
    f = UPLOADS_DIR / filename
    if f.exists():
        f.unlink()
    return {"deleted": filename}
