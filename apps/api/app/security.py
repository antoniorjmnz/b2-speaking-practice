from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, status


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def verify_session_token(token: str, expected_hash: str, pepper: str) -> bool:
    candidate = hash_session_token(token, pepper)
    return hmac.compare_digest(candidate, expected_hash)


def _signature(payload: str, secret: str) -> str:
    raw = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def create_scoped_signature(resource_id: str, secret: str, ttl_seconds: int) -> tuple[str, int]:
    expires = int(time.time()) + ttl_seconds
    return _signature(f"{resource_id}:{expires}", secret), expires


def verify_scoped_signature(resource_id: str, signature: str, expires: int, secret: str) -> bool:
    if expires < int(time.time()):
        return False
    expected = _signature(f"{resource_id}:{expires}", secret)
    return hmac.compare_digest(signature, expected)


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return token
