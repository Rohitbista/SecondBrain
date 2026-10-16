"""Business logic for authentication. Owns the DB transaction (commit/rollback)."""
import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.config.settings import settings
from secondbrain.database import auth_db
from secondbrain.database.models import User
from secondbrain.utils.email import send_password_reset_email, send_verification_email

logger = logging.getLogger(__name__)

VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"

_hasher = PasswordHasher()
# Used to burn the same CPU time when the user doesn't exist (timing attacks)
_DUMMY_HASH = _hasher.hash("not-a-real-password")

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


# ---------- helpers ----------
def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


async def _hash_password(password: str) -> str:
    # argon2 is CPU heavy: keep it off the event loop
    return await asyncio.to_thread(_hasher.hash, password)


def _create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def _issue_token(
    db: AsyncSession, user_id: int, purpose: str, ttl: timedelta
) -> str:
    """Create a fresh one-time token (invalidating older unused ones) and return the raw value."""
    await auth_db.delete_unused_tokens(db, user_id, purpose)
    raw = secrets.token_urlsafe(32)
    await auth_db.create_token(
        db,
        user_id=user_id,
        purpose=purpose,
        token_hash=_hash_token(raw),
        expires_at=datetime.now(timezone.utc) + ttl,
    )
    return raw


async def _send_email(sender, to_email: str, raw_token: str) -> None:
    """Background task wrapper: opens its own HTTP client and never raises."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await sender(client, to_email, raw_token)
    except Exception:
        logger.exception("Failed to send email to %s", to_email)


_VERIFY_TTL = lambda: timedelta(hours=settings.verification_token_ttl_hours)  # noqa: E731
_RESET_TTL = lambda: timedelta(minutes=settings.password_reset_token_ttl_minutes)  # noqa: E731


# ---------- register / verify ----------
async def register(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    email: str,
    first_name: str,
    last_name: str,
    username: str,
    password: str,
) -> User:
    email = email.strip().lower()
    username = username.strip().lower()

    if await auth_db.get_user_by_email(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    if await auth_db.get_user_by_username(db, username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    hashed = await _hash_password(password)
    try:
        user = await auth_db.create_user(
            db,
            email=email,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            username=username,
            hashed_password=hashed,
        )
        raw = await _issue_token(db, user.id, VERIFY_EMAIL, _VERIFY_TTL())
        await db.commit()
    except IntegrityError:  # lost a race with a parallel registration
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already in use")

    background_tasks.add_task(_send_email, send_verification_email, user.email, raw)
    return user


async def verify_email(db: AsyncSession, raw_token: str) -> None:
    user_id = await auth_db.consume_token(db, _hash_token(raw_token), VERIFY_EMAIL)
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification link")
    await auth_db.mark_verified(db, user_id)
    await db.commit()


async def resend_verification(
    db: AsyncSession, background_tasks: BackgroundTasks, email: str
) -> None:
    """Silent when the email is unknown or already verified (no account enumeration)."""
    user = await auth_db.get_user_by_email(db, email.strip().lower())
    if user and not user.is_verified:
        raw = await _issue_token(db, user.id, VERIFY_EMAIL, _VERIFY_TTL())
        await db.commit()
        background_tasks.add_task(_send_email, send_verification_email, user.email, raw)


# ---------- login / current user ----------
async def login(db: AsyncSession, identifier: str, password: str) -> str:
    """identifier can be the username or the email. Returns a JWT access token."""
    user = await auth_db.get_user_by_login(db, identifier.strip().lower())
    hashed = user.hashed_password if user else _DUMMY_HASH
    valid = await asyncio.to_thread(_verify_password, hashed, password)

    if not user or not valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username/email or password",
            headers=_UNAUTHORIZED,
        )
    if not user.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Email not verified. Check your inbox or request a new verification email.",
        )
    return _create_access_token(user.id)


async def get_user_from_token(db: AsyncSession, token: str) -> User:
    invalid = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers=_UNAUTHORIZED
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise invalid

    user = await auth_db.get_user_by_id(db, user_id)
    if not user or not user.is_verified:
        raise invalid
    return user


# ---------- forgot / reset password ----------
async def forgot_password(
    db: AsyncSession, background_tasks: BackgroundTasks, email: str
) -> None:
    """Silent when the email is unknown (no account enumeration)."""
    user = await auth_db.get_user_by_email(db, email.strip().lower())
    if user:
        raw = await _issue_token(db, user.id, RESET_PASSWORD, _RESET_TTL())
        await db.commit()
        background_tasks.add_task(_send_email, send_password_reset_email, user.email, raw)


async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> None:
    hashed = await _hash_password(new_password)  # hash first so a slow/failed hash can't burn the token
    user_id = await auth_db.consume_token(db, _hash_token(raw_token), RESET_PASSWORD)
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")

    await auth_db.set_password(db, user_id, hashed)
    await auth_db.mark_verified(db, user_id)  # they proved they own the inbox
    await auth_db.delete_unused_tokens(db, user_id, RESET_PASSWORD)
    await db.commit()