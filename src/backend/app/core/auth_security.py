# src/backend/app/core/security.py
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
import bcrypt

# ---------------------------------------------------------------------------
# Konfiguráció – ezek a .env-ből jönnek
# ---------------------------------------------------------------------------

SECRET_KEY: str = os.environ["SECRET_KEY"]          # legalább 32 random byte
ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")

ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)
REFRESH_TOKEN_EXPIRE_DAYS: int = int(
    os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7")
)

# ---------------------------------------------------------------------------
# Jelszó hashing
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id, "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id, "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str) -> str:
    """
    Dekódolja a tokent és visszaadja a user_id-t (sub claim).
    Hibás vagy lejárt token esetén JWTError-t dob.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise

    if payload.get("type") != expected_type:
        raise JWTError(f"Várt token típus: {expected_type}")

    sub: str | None = payload.get("sub")
    if sub is None:
        raise JWTError("Hiányzó 'sub' claim.")

    return sub
