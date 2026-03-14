"""
routes/auth.py
==============
Minimal email/password auth backed by MongoDB Atlas.

  POST /auth/register  — create a new user account
  POST /auth/login     — validate credentials, return user session

Security note: passwords are hashed with SHA-256 + a per-user random salt.
This is suitable for a hackathon demo. For production, use bcrypt/argon2
via passlib and add rate-limiting.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.db.mongodb import get_users_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Schema ────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class AuthResponse(BaseModel):
    id: str
    name: str
    email: str


def _hash_password(password: str, salt: str) -> str:
    """SHA-256 HMAC with a per-user salt."""
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register a new user account",
)
async def register(
    body: RegisterRequest,
) -> AuthResponse:

    if not (settings.mongodb_url or "").strip():
        raise HTTPException(status_code=503, detail="MONGODB_URL is not configured.")

    user_id = f"user_{secrets.token_hex(8)}"
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(body.password, salt)
    email = body.email.lower()
    users = get_users_collection()

    try:
        await users.insert_one(
            {
                "id": user_id,
                "name": body.name.strip(),
                "email": email,
                "salt": salt,
                "password_hash": pw_hash,
            }
        )
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        ) from exc

    logger.info("Registered new user | id=%s email=%s", user_id, email)
    return AuthResponse(id=user_id, name=body.name.strip(), email=email)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email and password",
)
async def login(
    body: LoginRequest,
) -> AuthResponse:

    if not (settings.mongodb_url or "").strip():
        raise HTTPException(status_code=503, detail="MONGODB_URL is not configured.")

    users = get_users_collection()
    email = body.email.lower()

    row = await users.find_one(
        {"email": email},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "salt": 1, "password_hash": 1},
    )

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    expected = _hash_password(body.password, row["salt"])
    if not secrets.compare_digest(expected, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    logger.info("Successful login | id=%s", row["id"])
    return AuthResponse(id=row["id"], name=row["name"], email=row["email"])
