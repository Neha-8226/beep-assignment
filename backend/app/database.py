"""Database Connection & Session Management.

Provides unified SQLAlchemy session factory supporting:
- Local development: embedded SQLite (jobs.db)
- Production: persistent hosted PostgreSQL (Supabase)
"""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import settings

# Configure engine parameters according to dialect
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # Production PostgreSQL (e.g. Supabase connection pooler)
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI and CLI dependency yielding a thread-safe database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all relational tables defined in SQLAlchemy models if they do not exist."""
    Base.metadata.create_all(bind=engine)
