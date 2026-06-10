# src/backend/app/routers/interactions.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.backend.app.core.database import get_db
from src.backend.app.core.auth_dependencies import get_current_user
from src.backend.app.models.models import ImplicitFeedback, Movie, User
from src.backend.app.schemas.interactions_schemas import (
    ImplicitFeedbackCreate,
    ImplicitFeedbackResponse,
)

router = APIRouter(prefix="/interactions", tags=["interactions"])


# ---------------------------------------------------------------------------
# POST /interactions  – implicit esemény rögzítése
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ImplicitFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_interaction(
    body: ImplicitFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImplicitFeedback:
    # Film létezik-e?
    movie = db.get(Movie, body.movie_id)
    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"A(z) {body.movie_id} azonosítójú film nem található.",
        )

    # duration_seconds csak view esetén értelmes
    duration = body.duration_seconds
    if body.event_type != "view" and duration is not None:
        duration = None

    feedback = ImplicitFeedback(
        id=uuid.uuid4(),
        user_id=current_user.id,
        movie_id=body.movie_id,
        event_type=body.event_type,
        duration_seconds=duration,
        session_id=body.session_id,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
