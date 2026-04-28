# src/backend/app/routers/profile.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from src.backend.app.core.database import get_db
from src.backend.app.core.auth_dependencies import get_current_user
from src.backend.app.core.auth_security import hash_password, verify_password
from src.backend.app.models.models import ImplicitFeedback, Rating, Recommendation, Tag, User
from src.backend.app.schemas.auth_schemas import UserResponse
from src.backend.app.schemas.profile_schemas import (
    DeleteAccountRequest,
    UpdateDisplayNameRequest,
    UpdatePasswordRequest,
)

router = APIRouter(prefix="/profile", tags=["profile"])


# ---------------------------------------------------------------------------
# PATCH /profile/display-name
# ---------------------------------------------------------------------------

@router.patch("/display-name", response_model=UserResponse)
def update_display_name(
    body: UpdateDisplayNameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    current_user.display_name = body.display_name
    db.commit()
    db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# PATCH /profile/password
# ---------------------------------------------------------------------------

@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(
    body: UpdatePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    # Seeded placeholder userek nem változtathatnak jelszót
    if current_user.hashed_password == "seeded_no_login":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ez a fiók nem támogatja a jelszóváltoztatást.",
        )

    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A jelenlegi jelszó helytelen.",
        )

    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Az új jelszó nem egyezhet meg a jelenlegivel.",
        )

    current_user.hashed_password = hash_password(body.new_password)
    db.commit()


# ---------------------------------------------------------------------------
# DELETE /profile
# ---------------------------------------------------------------------------

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    body: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if current_user.hashed_password == "seeded_no_login":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ez a fiók nem törölhető.",
        )

    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Helytelen jelszó.",
        )

    # Explicit törlés a CASCADE esetleges hiányára való tekintettel
    user_id = current_user.id
    for model in (Recommendation, ImplicitFeedback, Tag, Rating):
        db.execute(delete(model).where(model.user_id == user_id))

    db.delete(current_user)
    db.commit()
