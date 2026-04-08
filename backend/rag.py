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

QDRANT_URL = _os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = _os.getenv("QDRANT_API_KEY", None)
COLLECTION = "documents"
EMBED_MODEL = "text-embedding-3-small"

DEFAULT_CHUNK_SIZE = 600
DEFAULT_OVERLAP = 100

# Balanced retrieval
MIN_SEARCH_SCORE = 0.15
MAX_RAG_CHUNKS = 6

GROUNDING_SYSTEM_PROMPT = """
Du er en analytisk assistent som svarer basert på oppgitte kilder.

MÅL:
- Gi et presist og nyttig svar på norsk
- Vær forklarende når kildene støtter det
- Ikke legg til detaljer som ikke har dekning i teksten

REGLER:
1. Svar primært basert på kildene.
2. Hvis noe ikke er tydelig spesifisert i kildene, si det eksplisitt.
3. Du kan kombinere informasjon fra flere chunks når de støtter hverandre.
4. Ikke dikt opp konkrete detaljer som ikke finnes i teksten.
5. Bruk kildehenvisninger som [C1], [C2] når det er naturlig.
6. Unngå bastante påstander hvis grunnlaget er svakt.

SVARSTIL:
- Norsk
- Presis
- Gjerne litt utfyllende
- God flyt
""".strip()

MODELS = {
    "claude-sonnet-4-6": {"label": "Claude Sonnet 4.6 — anbefalt (Anthropic)", "provider": "anthropic"},
    "claude-haiku-4-5-20251001": {"label": "Claude Haiku 4.5 — rask (Anthropic)", "provider": "anthropic"},
    "claude-opus-4-6": {"label": "Claude Opus 4.6 — kraftigst (Anthropic)", "provider": "anthropic"},
    "gpt-4.1-mini": {"label": "GPT-4.1 Mini — rask, billig (OpenAI)", "provider": "openai"},
    "gpt-4o": {"label": "GPT-4o — kraftig (OpenAI)", "provider": "openai"},
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

    def chunk_text(
        self,
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> List[str]:
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

    def index_chunks(
        self,
        chunks: List[Dict],
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> int:
        """chunks: [{"source": str, "text": str, "page": int|None}]"""
        docs = []
        for i, c in enumerate(chunks):
            docs.append(
                {
                    "id": str(uuid.uuid4()),
                    "chunk_id": f"C{i+1}",
                    "source": c["source"],
                    "page": c.get("page"),
                    "text": c["text"],
                }
            )

        if not docs:
            return 0

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
            self.qdrant.upsert(collection_name=COLLECTION, points=points[i : i + batch_size])

        return len(docs)

    def search(self, query: str, limit: int = 8, min_score: float = MIN_SEARCH_SCORE) -> List[dict]:
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

        results = [
            {
                "chunk_id": p.payload.get("chunk_id", ""),
                "source": p.payload.get("source", "ukjent"),
                "page": p.payload.get("page"),
                "text": p.payload.get("text", ""),
                "score": round(float(p.score), 4),
            }
            for p in points
        ]

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

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
            {
                "chunk_id": p.payload.get("chunk_id", ""),
                "text": p.payload.get("text", ""),
                "page": p.payload.get("page"),
            }
            for p in results
        ]

    def summarize_document(self, source: str, model: str) -> str:
        chunks = self.get_source_chunks(source)
        if not chunks:
            raise RuntimeError(f"Ingen innhold funnet for: {source}")

        text = "\n\n".join(c["text"] for c in chunks[:15])
        prompt = (
            f"Les følgende tekst fra dokumentet «{source}» og lag et kort, presist sammendrag "
            f"på 3–5 setninger på norsk.\n\nTekst:\n{text}\n\nSammendrag:"
        )

        provider = MODELS[model]["provider"]
        if provider == "anthropic":
            if not self.anthropic_client:
                raise RuntimeError("Anthropic API-nøkkel mangler.")
            resp = self.anthropic_client.messages.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return resp.content[0].text.strip()

        resp = self.openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    # ---------- RAG helpers ----------

    def _filter_points_for_rag(
        self,
        points: List[dict],
        min_score: float = 0.35,
        max_chunks: int = MAX_RAG_CHUNKS,
    ) -> List[dict]:
        filtered = [p for p in points if p.get("score") is not None and p["score"] >= min_score]
        filtered.sort(key=lambda x: x["score"], reverse=True)

        if filtered:
            return filtered[:max_chunks]

        fallback = [p for p in points if p.get("score") is not None]
        fallback.sort(key=lambda x: x["score"], reverse=True)
        return fallback[: min(len(fallback), 3)]

    def _build_rag_context(self, points: List[dict]) -> str:
        parts = []
        for p in points:
            meta = [f"Kilde: {p['source']}"]
            if p.get("page") is not None:
                meta.append(f"Side: {p['page']}")
            if p.get("score") is not None:
                meta.append(f"Score: {p['score']}")
            meta_str = ", ".join(meta)
            parts.append(f"[{p['chunk_id']}] ({meta_str})\n{p['text']}")
        return "\n\n".join(parts)

    # ---------- RAG ----------

    def rag_answer(self, query: str, points: List[dict], model: str) -> dict:
        grounded_points = self._filter_points_for_rag(points)

        if not grounded_points:
            return {
                "answer": "Jeg finner ikke tilstrekkelig relevant informasjon i kildene til å svare sikkert.",
                "used_chunks": [],
                "notes": "Ingen relevante chunks tilgjengelig.",
            }

        valid_ids = [p["chunk_id"] for p in grounded_points]
        context = self._build_rag_context(grounded_points)

        prompt = f"""
Svar på spørsmålet basert på kildene under.

Du skal:
- Gi et presist og nyttig svar på norsk
- Gjerne være noe utfyllende hvis kildene støtter det
- Si tydelig fra hvis noe ikke er spesifisert eller uklart

Returner REN JSON (ingen markdown) med nøyaktig disse feltene:
{{
  "answer": "presist svar på norsk, gjerne 3–7 setninger",
  "used_chunks": ["C1", "C2"],
  "notes": "valgfritt"
}}

KRAV:
- Gyldige chunk_id-er er KUN: {valid_ids}
- Du kan IKKE bruke andre chunk_id-er enn disse
- Ikke dikt opp detaljer som ikke har dekning i teksten
- Bruk [C1], [C2] i selve teksten når det passer naturlig
- Hvis noe ikke fremgår tydelig, si det eksplisitt

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
                system=GROUNDING_SYSTEM_PROMPT + "\n\nDu returnerer kun gyldig JSON.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            raw = resp.content[0].text.strip()
        else:
            resp = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": GROUNDING_SYSTEM_PROMPT + "\n\nDu returnerer kun gyldig JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            raw = resp.choices[0].message.content.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                data = json.loads(raw[start : end + 1])
            else:
                raise

        used_chunks = data.get("used_chunks", [])
        used_chunks = [c for c in used_chunks if c in valid_ids]
        data["used_chunks"] = used_chunks

        if "answer" not in data or not isinstance(data["answer"], str):
            data["answer"] = "Jeg finner ikke dette tydelig i kildene."

        if "notes" not in data:
            data["notes"] = ""

        return data

    def stream_answer(self, query: str, points: List[dict], model: str):
        """Sync generator: yields {"type":"token","text":str}, then {"type":"done","answer":str,"used_chunks":[...]}"""
        grounded_points = self._filter_points_for_rag(points)

        if not grounded_points:
            yield {
                "type": "done",
                "answer": "Jeg finner ikke tilstrekkelig relevant informasjon i kildene til å svare sikkert.",
                "used_chunks": [],
            }
            return

        valid_ids = [p["chunk_id"] for p in grounded_points]
        context = self._build_rag_context(grounded_points)

        prompt = f"""Svar på spørsmålet basert på kildene under.

REGLER:
- Svar på norsk
- Svar presist, gjerne litt utfyllende
- Bruk kildene aktivt
- Ikke dikt opp detaljer som ikke har dekning i teksten
- Hvis noe er uklart eller ikke spesifisert, si det tydelig
- Bruk [C1], [C2] osv. underveis når det er naturlig
- Avslutt med en egen linje:
Kilder: C1, C2

Spørsmål:
{query}

Kilder:
{context}""".strip()

        provider = MODELS[model]["provider"]
        full_text = ""

        if provider == "anthropic":
            if not self.anthropic_client:
                raise RuntimeError("Anthropic API-nøkkel mangler.")
            with self.anthropic_client.messages.stream(
                model=model,
                max_tokens=1024,
                system=GROUNDING_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    yield {"type": "token", "text": text}
        else:
            for chunk in self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                stream=True,
            ):
                text = chunk.choices[0].delta.content or ""
                if text:
                    full_text += text
                    yield {"type": "token", "text": text}

        used_chunks = []
        answer = full_text.strip()

        if "Kilder:" in full_text:
            parts = full_text.rsplit("Kilder:", 1)
            answer = parts[0].strip()
            ids = re.findall(r"C\d+", parts[1])
            used_chunks = [c for c in ids if c in valid_ids]

        yield {"type": "done", "answer": answer, "used_chunks": used_chunks}
