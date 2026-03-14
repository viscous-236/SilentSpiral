"""
app/db/mongodb.py
=================
Async MongoDB helpers for Atlas-backed auth persistence.

Provides:
  - Mongo async client singleton
  - Users collection accessor
  - Startup initializer for connectivity + unique email index
"""

from __future__ import annotations

import logging
from functools import lru_cache
from urllib.parse import quote_plus, unquote, urlsplit, urlunsplit

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import InvalidURI, ServerSelectionTimeoutError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _encode_mongodb_credentials(url: str) -> str:
    """
    Ensure MongoDB username/password are percent-encoded.

    Atlas passwords frequently contain reserved URL characters (e.g. '@', ':').
    If left unescaped, PyMongo raises InvalidURI during startup.
    """
    parts = urlsplit(url)
    if not parts.netloc or "@" not in parts.netloc:
        return url

    # Split on the last '@' so passwords containing '@' remain intact.
    raw_userinfo, host_part = parts.netloc.rsplit("@", 1)
    if not raw_userinfo:
        return url

    if ":" in raw_userinfo:
        raw_username, raw_password = raw_userinfo.split(":", 1)
    else:
        raw_username, raw_password = raw_userinfo, None

    if not raw_username:
        return url

    username = quote_plus(unquote(raw_username))
    if raw_password is None:
        userinfo = username
    else:
        password = quote_plus(unquote(raw_password))
        userinfo = f"{username}:{password}"

    netloc = f"{userinfo}@{host_part}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@lru_cache(maxsize=1)
def _get_mongodb_url() -> str:
    raw = (settings.mongodb_url or "").strip()
    if not raw:
        raise RuntimeError("MONGODB_URL is not configured.")
    return _encode_mongodb_credentials(raw)


@lru_cache(maxsize=1)
def get_mongo_client() -> AsyncIOMotorClient:
    """Create and cache the MongoDB async client."""
    url = _get_mongodb_url()

    logger.info("Initialising MongoDB Atlas client for auth persistence.")
    try:
        return AsyncIOMotorClient(
            url,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
        )
    except InvalidURI as exc:
        raise RuntimeError(
            "Invalid MONGODB_URL. If your Atlas password contains special "
            "characters, URL-encode them."
        ) from exc


def get_users_collection() -> AsyncIOMotorCollection:
    """Return the configured MongoDB users collection."""
    if not (settings.mongodb_url or "").strip():
        raise RuntimeError("MONGODB_URL is not configured.")

    client = get_mongo_client()
    db = client[settings.mongodb_db_name]
    return db[settings.mongodb_users_collection]


async def init_mongodb() -> None:
    """
    Verify Mongo connectivity and ensure required indexes exist.

    We keep auth schema minimal and compatible with existing route logic.
    """
    if not (settings.mongodb_url or "").strip():
        logger.warning(
            "Skipping MongoDB initialisation because MONGODB_URL is not configured. "
            "Auth routes will fail until MONGODB_URL is set."
        )
        return

    users = get_users_collection()

    # Connectivity check with a simple command against the selected DB.
    try:
        await users.database.command("ping")
    except ServerSelectionTimeoutError as exc:
        raise RuntimeError(
            "MongoDB Atlas is unreachable (server selection timeout). "
            "Check Atlas Network Access IP allowlist, ensure the cluster allows public access "
            "(not private-endpoint-only), and verify your network allows outbound TLS to port 27017."
        ) from exc

    # Case-insensitive uniqueness is enforced by storing emails in lowercase.
    await users.create_index("email", unique=True, name="users_email_unique_idx")

    logger.info("MongoDB collections and indexes are ready.")


def close_mongo_client() -> None:
    """Close and clear cached MongoDB client."""
    if not (settings.mongodb_url or "").strip():
        return

    try:
        client = get_mongo_client()
    except RuntimeError:
        return

    client.close()
    get_mongo_client.cache_clear()
