"""
app/db/postgres.py
==================
Async Postgres helpers for managed Postgres persistence (Neon/Supabase/etc.).

Provides:
  - SQLAlchemy async engine/session factory (asyncpg driver)
  - FastAPI dependency for DB sessions
  - Startup initializer for auth table creation
"""

from __future__ import annotations

import logging
from functools import lru_cache
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)


_ASYNC_PG_UNSUPPORTED_QUERY_PARAMS = {
    "channel_binding",
    "gssencmode",
    "krbsrvname",
    "requirepeer",
    "sslcert",
    "sslcrl",
    "sslkey",
    "sslmode",
    "sslpassword",
    "sslrootcert",
    "target_session_attrs",
}


def _encode_database_credentials(url: str) -> str:
    """
    Ensure username/password are percent-encoded for SQLAlchemy URL parsing.

    Managed Postgres providers often generate passwords with reserved URL
    characters (e.g. '@'). Without encoding, SQLAlchemy may mis-parse hostnames
    and fail with gaierror.
    """
    parts = urlsplit(url)
    if not parts.hostname:
        return url

    username = parts.username
    password = parts.password

    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    host_port = host
    if parts.port is not None:
        host_port = f"{host}:{parts.port}"

    if username is None:
        userinfo = ""
    elif password is None:
        userinfo = quote(username, safe="")
    else:
        userinfo = f"{quote(username, safe='')}:{quote(password, safe='')}"

    netloc = f"{userinfo}@{host_port}" if userinfo else host_port
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _strip_unsupported_asyncpg_query_params(url: str) -> str:
    """
    Drop libpq-style URL params that asyncpg does not accept as kwargs.

    Neon pooled URLs often include `sslmode` and `channel_binding`; SQLAlchemy's
    asyncpg dialect forwards query params to asyncpg.connect(), where these cause:
    TypeError: connect() got an unexpected keyword argument ...
    """
    parts = urlsplit(url)
    if not parts.query:
        return url

    params = parse_qsl(parts.query, keep_blank_values=True)
    filtered = [(k, v) for (k, v) in params if k.lower() not in _ASYNC_PG_UNSUPPORTED_QUERY_PARAMS]
    if len(filtered) == len(params):
        return url

    query = urlencode(filtered, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _normalise_database_url(url: str) -> str:
    """
    Convert common Postgres URL variants to SQLAlchemy asyncpg format.

    Supports:
      - postgres://...
      - postgresql://...
      - postgresql+asyncpg://...
    """
    normalized = url.strip()

    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://") :]

    if normalized.startswith("postgresql://") and not normalized.startswith("postgresql+asyncpg://"):
        normalized = "postgresql+asyncpg://" + normalized[len("postgresql://") :]

    normalized = _encode_database_credentials(normalized)
    return _strip_unsupported_asyncpg_query_params(normalized)


@lru_cache(maxsize=1)
def _get_database_url() -> str:
    raw = (settings.neon_database_url or settings.database_url).strip()
    if not raw:
        raise RuntimeError("NEON_DATABASE_URL/DATABASE_URL is not configured.")
    return _normalise_database_url(raw)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create and cache the SQLAlchemy async engine."""
    url = _get_database_url()
    logger.info("Initialising managed Postgres engine for auth persistence.")
    return create_async_engine(
        url,
        pool_pre_ping=True,
        future=True,
        connect_args={
            "ssl": "require",
            "timeout": 10,
            "command_timeout": 30,
        },
    )


@lru_cache(maxsize=1)
def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_db():
    """FastAPI dependency that yields an async DB session."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        yield session


async def init_db() -> None:
    """
    Create required tables/indexes if missing.

    We keep auth schema minimal and compatible with existing route logic.
    """
    if not (settings.neon_database_url or settings.database_url).strip():
        logger.warning(
            "Skipping DB initialisation because no Postgres URL is configured "
            "(set NEON_DATABASE_URL or DATABASE_URL)."
        )
        return

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    email         TEXT NOT NULL,
                    salt          TEXT NOT NULL,
                    password_hash TEXT NOT NULL
                )
                """
            )
        )

        # Case-insensitive uniqueness for email, equivalent to SQLite NOCASE behavior.
        await conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx
                ON users ((lower(email)))
                """
            )
        )

    logger.info("Postgres schema is ready.")
