"""
feedback.py — SQLAlchemy model and DB helpers for RAG answer feedback.

Local dev:   SQLite  (auto-created as ./feedback.db, no config needed)
Production:  Postgres via DATABASE_URL env var (Supabase or any Postgres)

Supabase example:
  DATABASE_URL=postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres

Note: Render/Heroku expose "postgres://" — we normalise to "postgresql://" below.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./feedback.db")

# SQLAlchemy requires "postgresql://" — Supabase/Heroku/Render use "postgres://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class FeedbackEntry(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # --- Identifiers ---
    conversation_id = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True)          # Supabase JWT sub-claim

    # --- Feedback content ---
    rating = Column(Integer, nullable=False)         # 1 = thumbs up, -1 = thumbs down
    category = Column(String, nullable=True)         # populated on thumbs down only
    comment = Column(Text, nullable=True)

    # --- Query context ---
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    model = Column(String(100), nullable=False)
    prompt_version = Column(String(100), nullable=True)  # git short hash at runtime

    # --- Retrieval context (JSONB in Postgres, TEXT in SQLite) ---
    search_results = Column(JSON, nullable=True)     # [{chunk_id, source, score, text}]
    used_chunks = Column(JSON, nullable=True)        # ["C1", "C2"]

    # --- Latency (milliseconds, measured in frontend) ---
    latency_search_ms = Column(Integer, nullable=True)
    latency_generation_ms = Column(Integer, nullable=True)


def init_db() -> None:
    """Create tables if they don't exist. Called once at app startup."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
