import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import config


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def create_token(user_id: int, branch_id: int | None, roles: list[str], token_type: str) -> str:
    if token_type == "access":
        expire = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=config.REFRESH_TOKEN_DAYS)
    # NOTE: never put passwords or secrets in the JWT payload (spec §9.1).
    payload = {
        "sub": str(user_id),
        "branch_id": branch_id,
        "roles": roles,
        "type": token_type,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def create_invite_token(applicant_id: int, email: str) -> str:
    """Signed, expiring invitation token (valid 14 days)."""
    payload = {
        "sub": str(applicant_id),
        "email": email,
        "type": "invite",
        "exp": datetime.now(timezone.utc) + timedelta(days=14),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
