"""Database engine and session factory.

Supports SQLite (for testing) and PostgreSQL (production).
Uses SQLAlchemy connection pooling with sensible defaults:
- QueuePool for PostgreSQL (default): Manages a queue of persistent connections
- NullPool for SQLite: No pooling (SQLite can't handle concurrent connections well)

The session factory is injected by the lifespan context manager in main.py.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool, NullPool

# Determine which database to use
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./takehome.db")

# Create engine with appropriate pooling strategy
if DATABASE_URL.startswith("postgresql"):
    # PostgreSQL: Use QueuePool for connection pooling
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=10,              # Number of persistent connections to keep
        max_overflow=20,            # Additional connections to allow when pool exhausted
        pool_recycle=3600,          # Recycle connections after 1 hour
        pool_pre_ping=True,         # Test connections before using (handles lost connections)
        echo=False,
    )
else:
    # SQLite: Use NullPool (no connection pooling)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_engine():
    """Return the configured SQLAlchemy engine."""
    return engine


def get_session_factory():
    """Return the configured session factory."""
    return SessionLocal

