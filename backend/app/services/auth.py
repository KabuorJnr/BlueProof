"""PIN hashing, signed tokens, and the request dependencies that enforce roles.

Standard library only. The token is a compact HMAC-SHA256 signed payload, not a
full JWT, because the one thing this system needs from a token is "which user,
which role, until when", and every extra feature of a JWT library is a feature
somebody can misconfigure.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..models import STAFF_ROLES, Role, User

_ITERATIONS = 200_000


def valid_pin(pin: str) -> bool:
    return pin.isdigit() and 4 <= len(pin) <= 8


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def check_pin(pin: str, stored: str | None) -> bool:
    if not stored:
        # Still spend the time, so a missing account is not faster to probe.
        hashlib.pbkdf2_hmac("sha256", pin.encode(), b"0" * 16, _ITERATIONS)
        return False
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str) -> str:
    return _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())


def issue_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "role": user.role.value if isinstance(user.role, Role) else user.role,
        "exp": int(time.time()) + settings.token_ttl_hours * 3600,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body)}"


def read_token(token: str) -> dict | None:
    try:
        body, sig = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def login(session: Session, user: User | None, pin: str) -> str:
    """Check a PIN with lockout. Returns a token or raises 401/423."""
    now = datetime.now(timezone.utc)
    if user is not None and user.locked_until is not None:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise HTTPException(423, "Too many wrong PINs. Try again later.")

    if user is None or not check_pin(pin, user.pin_hash):
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_login_attempts:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
            session.add(user)
            session.commit()
        # One message for both cases, so the endpoint does not reveal which
        # phone numbers are enrolled.
        raise HTTPException(401, "Phone number or PIN is wrong.")

    user.failed_logins = 0
    user.locked_until = None
    session.add(user)
    session.commit()
    return issue_token(user)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def optional_user(request: Request, session: Session = Depends(get_session)) -> User | None:
    token = _bearer(request)
    if not token:
        return None
    payload = read_token(token)
    if payload is None:
        raise HTTPException(401, "Session expired. Sign in again.")
    user = session.get(User, payload["sub"])
    if user is None:
        raise HTTPException(401, "Account no longer exists.")
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in required.", headers={"WWW-Authenticate": "Bearer"})
    return user


def is_staff(user: User | None) -> bool:
    return user is not None and user.role in STAFF_ROLES


def require_staff(user: User = Depends(current_user)) -> User:
    if not is_staff(user):
        raise HTTPException(403, "This needs a CFA lead, verifier or admin.")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(403, "Admin only.")
    return user
