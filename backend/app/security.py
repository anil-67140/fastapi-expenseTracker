"""Password hashing (Argon2 via pwdlib) and JWT creation/verification (PyJWT)."""
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import settings
from app.exceptions import UnauthorizedError

password_hash = PasswordHash.recommended()  # Argon2id, salted automatically
# Used to burn the same CPU time when an email does not exist (prevents user enumeration by timing).
DUMMY_HASH = password_hash.hash("not-a-real-password")


def hash_password(plain: str) -> str:
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds). `sub` is the user id; `exp` makes it expire."""
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "iat": now, "exp": now + delta}
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, int(delta.total_seconds())


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired. Please log in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token.") from exc
    subject = payload.get("sub")
    if not subject:
        raise UnauthorizedError("Invalid token.")
    return subject
