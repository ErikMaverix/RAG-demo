"""
rag.py — All core RAG logic, extracted from app_v2.py
"""
from __future__ import annotations

import json
import re
import uuid
from io import BytesIO
from typing import List, Dict, Optional

from docx import Document
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from openai import OpenAI

# -------------------- Config --------------------
import os as _os
QDRANT_URL = _os.getenv('QDRANT_URL', 'http://localhost:6333')
QDRANT_API_KEY = _os.getenv('QDRANT_API_KEY', None)
COLLECTION = "documents"
EMBED_MODEL = "text-embedding-3-small"
DEFAULT_CHUNK_SIZE = 600
DEFAULT_OVERLAP = 100

MODELS = {
    "claude-sonnet-4-6":         {"label": "Claude Sonnet 4.6 — anbefalt (Anthropic)", "provider": "anthropic"},
    "claude-haiku-4-5-20251001": {"label": "Claude Haiku 4.5 — rask (Anthropic)",     "provider": "anthropic"},
    "claude-opus-4-6":           {"label": "Claude Opus 4.6 — kraftigst (Anthropic)",  "provider": "anthropic"},
    "gpt-4.1-mini":              {"label": "GPT-4.1 Mini — rask, billig (OpenAI)",     "provider": "openai"},
    "gpt-4o":                    {"label": "GPT-4o — kraftig (OpenAI)",                "provider": "openai"},
}


class RAGEngine:
    def __init__(self, openai_api_key: str, anthropic_api_key: Optional[str] = None):
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.anthropic_client = None
        if anthropic_api_key:
            from anthropic import Anthropic
            self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        self.qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # ---------- Text extraction ----------

    def extract_text_from_bytes(self, data: bytes, filename: str) -> List[Dict]:
        """Returns list of {"text": str, "page": int | None}."""
        name = filename.lower()

        if name.endswith(".txt"):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1", errors="ignore")
            return [{"text": text, "page": None}]

        if name.endswith(".docx"):
            doc = Document(BytesIO(data))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            return [{"text": "\n".join(parts), "page": None}]

        if name.endswith(".pdf"):
            reader = PdfReader(BytesIO(data))
            pages = []
            for i, page in enumerate(reader.pages):
                t = page.extract_text() or ""
                if t.strip():
                    pages.append({"text": t, "page": i + 1})
            return pages

        raise ValueError(f"Ukjent filtype: {filename}. Bruk .txt, .docx eller .pdf")

    # ---------- Chunking ----------

    def chunk_text(self, text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        if not paragraphs:
            return []

        split_paras: List[str] = []
        for para in paragraphs:
            if len(para) <= chunk_size:
                split_paras.append(para)
            else:
                start = 0
                while start < len(para):
                    end = min(start + chunk_size, len(para))
                    split_paras.append(para[start:end])
                    if end == len(para):
                        break
                    start = end - overlap

        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for para in split_paras:
            if current_len + len(para) > chunk_size and current:
                chunks.append("\n\n".join(current))
                overlap_parts: List[str] = []
                overlap_len = 0
                for p in reversed(current):
                    if overlap_len + len(p) <= overlap:
                        overlap_parts.insert(0, p)
                        overlap_len += len(p)
                    else:
                        break
                current = overlap_parts
                current_len = sum(len(p) for p in current)
            current.append(para)
            current_len += len(para)

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    # ---------- Embeddings ----------

    def make_embedding_text(self, doc: dict) -> str:
        source = doc.get("source", "ukjent dokument")
        page = doc.get("page")
        text = doc.get("text", "")
        parts = [f"Dokument: {source}"]
        if page is not None:
            parts.append(f"Side: {page}")
        parts.append(f"Innhold: {text}")
        return "\n".join(parts)

    def make_query_text(self, query: str) -> str:
        return f"Spørsmål om innhold i dokumenter: {query.strip()}"

    def embed(self, texts: List[str]) -> List[List[float]]:
        resp = self.openai_client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [d.embedding for d in resp.data]

    # ---------- Qdrant ----------

    def ensure_collection(self, vector_size: int) -> None:
        if self.qdrant.collection_exists(COLLECTION):
            info = self.qdrant.get_collection(COLLECTION)
            if info.config.params.vectors.size != vector_size:
                self.qdrant.delete_collection(COLLECTION)
        if not self.qdrant.collection_exists(COLLECTION):
            self.qdrant.create_collection(
                collection_name=COLLECTION,
                vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
            )

    def index_chunks(self, chunks: List[Dict], chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> int:
        """chunks: [{"source": str, "text": str, "page": int|None}]"""
        docs = []
        for i, c in enumerate(chunks):
            docs.append({
                "id": str(uuid.uuid4()),
                "chunk_id": f"C{i+1}",
                "source": c["source"],
                "page": c.get("page"),
                "text": c["text"],
            })

        embedding_inputs = [self.make_embedding_text(d) for d in docs]
        vectors = self.embed(embedding_inputs)
        self.ensure_collection(len(vectors[0]))

        points = [
            qm.PointStruct(
                id=docs[i]["id"],
                vector=vectors[i],
                payload={
                    "chunk_id": docs[i]["chunk_id"],
                    "source": docs[i]["source"],
                    "page": docs[i].get("page"),
                    "text": docs[i]["text"],
                },
            )
            for i in range(len(docs))
        ]

        batch_size = 100
        for i in range(0, len(points), batch_size):
            self.qdrant.upsert(collection_name=COLLECTION, points=points[i:i + batch_size])
        return len(docs)

    def search(self, query: str, limit: int = 5, min_score: float = 0.15) -> List[dict]:
        if not self.qdrant.collection_exists(COLLECTION):
            raise RuntimeError("Collection finnes ikke. Indekser dokumenter først.")

        q_vec = self.embed([self.make_query_text(query)])[0]
        res = self.qdrant.query_points(
            collection_name=COLLECTION,
            query=q_vec,
            limit=limit,
            with_payload=True,
        )

        points = [p for p in res.points if p.score is not None and p.score >= min_score]
        return [
            {
                "chunk_id": p.payload.get("chunk_id", ""),
                "source": p.payload.get("source", "ukjent"),
                "page": p.payload.get("page"),
                "text": p.payload.get("text", ""),
                "score": round(p.score, 4),
            }
            for p in points
        ]

    def delete_collection(self) -> None:
        if self.qdrant.collection_exists(COLLECTION):
            self.qdrant.delete_collection(COLLECTION)

    def delete_by_source(self, source: str) -> None:
        if not self.qdrant.collection_exists(COLLECTION):
            return
        self.qdrant.delete(
            collection_name=COLLECTION,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="source", match=qm.MatchValue(value=source))]
                )
            ),
        )

    def get_source_chunks(self, source: str, limit: int = 20) -> List[dict]:
        if not self.qdrant.collection_exists(COLLECTION):
            return []
        results, _ = self.qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="source", match=qm.MatchValue(value=source))]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {"chunk_id": p.payload.get("chunk_id", ""), "text": p.payload.get("text", ""), "page": p.payload.get("page")}
            for p in results
        ]

    def summarize_document(self, source: str, model: str) -> str:
        chunks = self.get_source_chunks(source)
        if not chunks:
            raise RuntimeError(f"Ingen innhold funnet for: {source}")
        text = "\n\n".join(c["text"] for c in chunks[:15])
        prompt = f"Les følgende tekst fra dokumentet «{source}» og lag et kort, presist sammendrag på 3–5 setninger på norsk.\n\nTekst:\n{text}\n\nSammendrag:"
        provider = MODELS[model]["provider"]
        if provider == "anthropic":
            if not self.anthropic_client:
                raise RuntimeError("Anthropic API-nøkkel mangler.")
            resp = self.anthropic_client.messages.create(
                model=model, max_tokens=512,
                messages=[{"role": "user", "content": prompt}], temperature=0.3,
            )
            return resp.content[0].text.strip()
        else:
            resp = self.openai_client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], temperature=0.3,
            )
            return resp.choices[0].message.content.strip()

    # ---------- RAG ----------

    def rag_answer(self, query: str, points: List[dict], model: str) -> dict:
        sources = [{"chunk_id": p["chunk_id"], "source": p["source"], "text": p["text"]} for p in points]
        valid_ids = [s["chunk_id"] for s in sources]
        context = "\n\n".join(f"[{s['chunk_id']}] (Kilde: {s['source']}) {s['text']}" for s in sources)

        prompt = f"""
Svar på spørsmålet KUN basert på kildene under.
Hvis kildene ikke er nok til å svare: si "Jeg finner ikke dette i kildene."

Returner REN JSON (ingen markdown) med nøyaktig disse feltene:
{{
  "answer": "2–6 setninger på norsk",
  "used_chunks": ["C1","C3"],
  "notes": "valgfritt"
}}

Regler:
- Gyldige chunk_id-er er KUN: {valid_ids}
- Du kan IKKE oppgi andre chunk_id-er enn de som er listet over.

Spørsmål:
{query}

Kilder:
{context}
""".strip()

        provider = MODELS[model]["provider"]

        if provider == "anthropic":
            if not self.anthropic_client:
                raise RuntimeError("Anthropic API-nøkkel mangler.")
            resp = self.anthropic_client.messages.create(
                model=model,
                max_tokens=1024,
                system="Du returnerer kun gyldig JSON.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            raw = resp.content[0].text.strip()
        else:
            resp = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Du returnerer kun gyldig JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            raw = resp.choices[0].message.content.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                return json.loads(raw[start:end + 1])
            raise

    def stream_answer(self, query: str, points: List[dict], model: str):
        """Sync generator: yields {"type":"token","text":str}, then {"type":"done","answer":str,"used_chunks":[...]}"""
        sources = [{"chunk_id": p["chunk_id"], "source": p["source"], "text": p["text"]} for p in points]
        valid_ids = [s["chunk_id"] for s in sources]
        context = "\n\n".join(f"[{s['chunk_id']}] (Kilde: {s['source']}) {s['text']}" for s in sources)

        prompt = f"""Svar på spørsmålet KUN basert på kildene under. Svar på norsk, 2–6 setninger.
Bruk [C1], [C3] etc. for å referere til kildene underveis i teksten.
Avslutt med en linje som starter med "Kilder:" og lister opp chunk_id-ene du brukte, f.eks: Kilder: C1, C3
Hvis kildene ikke er nok: si "Jeg finner ikke dette i kildene."

Spørsmål: {query}

Kilder:
{context}""".strip()

        provider = MODELS[model]["provider"]
        full_text = ""

        if provider == "anthropic":
            if not self.anthropic_client:
                raise RuntimeError("Anthropic API-nøkkel mangler.")
            with self.anthropic_client.messages.stream(
                model=model, max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    yield {"type": "token", "text": text}
        else:
            for chunk in self.openai_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, stream=True,
            ):
                text = chunk.choices[0].delta.content or ""
                if text:
                    full_text += text
                    yield {"type": "token", "text": text}

        # Parse answer and used_chunks from the streamed text
        used_chunks = []
        answer = full_text
        if "Kilder:" in full_text:
            parts = full_text.rsplit("Kilder:", 1)
            answer = parts[0].strip()
            ids = re.findall(r'C\d+', parts[1])
            used_chunks = [c for c in ids if c in valid_ids]

        yield {"type": "done", "answer": answer, "used_chunks": used_chunks}
