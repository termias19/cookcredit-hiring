"""
CookCredit database connection module.

Uses SQLAlchemy for connection pooling and session management.
Supports both Cloud SQL (via Unix socket or Auth Proxy) and direct TCP connections.

Environment variables:
  DATABASE_URL          - Full connection string (preferred)
                          e.g. postgresql://user:pass@localhost:5432/cookcredit
  CLOUD_SQL_CONNECTION  - Cloud SQL instance connection name (for Unix socket)
                          e.g. project:region:instance
  DB_USER, DB_PASS, DB_NAME - Fallback individual vars (used with CLOUD_SQL_CONNECTION)
"""

import os
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text, URL
from sqlalchemy.orm import sessionmaker, declarative_base

log = logging.getLogger(__name__)

Base = declarative_base()


def _build_url():
    """Resolve the database URL from environment."""
    # Option 1: Explicit DATABASE_URL (local dev, Cloud Run with Auth Proxy)
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # Option 2: Cloud SQL Unix socket (Cloud Run native)
    conn_name = os.environ.get("CLOUD_SQL_CONNECTION")
    if conn_name:
        user = os.environ["DB_USER"]
        pw = os.environ["DB_PASS"]
        db = os.environ.get("DB_NAME", "cookcredit")
        socket_dir = os.environ.get("DB_SOCKET_DIR", "/cloudsql")
        return URL.create('postgresql+psycopg2', username=user, password=pw,
                          database=db, query={'host': f'{socket_dir}/{conn_name}'})

    raise RuntimeError(
        "No database configured. Set DATABASE_URL or CLOUD_SQL_CONNECTION + DB_USER + DB_PASS."
    )


engine = None
SessionLocal = None


def init_db():
    """Initialize the database engine and session factory. Call once at app startup."""
    global engine, SessionLocal
    url = _build_url()
    pool_size = max(1, min(20, int(os.environ.get('DB_POOL_SIZE', '5'))))
    max_overflow = max(0, min(40, int(os.environ.get('DB_MAX_OVERFLOW', '10'))))
    engine = create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=15,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    log.info("Database engine initialized (pool_size=%s max_overflow=%s)", pool_size, max_overflow)


def get_session():
    """Get a new database session. Caller must close it."""
    if SessionLocal is None:
        init_db()
    return SessionLocal()


@contextmanager
def db_session():
    """Context manager for database sessions. Auto-commits on success, rolls back on error."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection():
    """Verify database connectivity. Returns True if OK."""
    try:
        with db_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error("Database connection check failed: %s", e)
        return False
