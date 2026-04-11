# src/backend/app/core/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from src.backend.app.core.database import get_db
from src.backend.app.core.auth_security import decode_token
from src.backend.app.models.models import User

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency – visszaadja a bejelentkezett User objektumot.
    Használat: current_user: User = Depends(get_current_user)
    """
    token = credentials.credentials
    try:
        user_id = decode_token(token, expected_type="access")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Érvénytelen vagy lejárt access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A felhasználó nem található.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
