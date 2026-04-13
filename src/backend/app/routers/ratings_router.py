# src/backend/app/routers/ratings.py
import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.core.database import get_db
from src.backend.app.core.auth_dependencies import get_current_user
from src.backend.app.models.models import Movie, Rating, User
from src.backend.app.schemas.interactions_schemas import (
    PaginatedRatings,
    RatingCreate,
    RatingResponse,
    RatingUpdate,
)

router = APIRouter(prefix="/ratings", tags=["ratings"])


# ---------------------------------------------------------------------------
# GET /ratings  – saját értékelések listája
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedRatings)
def list_my_ratings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedRatings:
    base = select(Rating).where(Rating.user_id == current_user.id)

    total: int = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    ratings = db.execute(
        base.order_by(Rating.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    return PaginatedRatings(
        items=ratings,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


# ---------------------------------------------------------------------------
# POST /ratings  – értékelés létrehozása
# ---------------------------------------------------------------------------

@router.post("", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
def create_rating(
    body: RatingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Rating:
    # Film létezik-e?
    movie = db.get(Movie, body.movie_id)
    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"A(z) {body.movie_id} azonosítójú film nem található.",
        )

    # Már értékelte-e?
    existing = db.execute(
        select(Rating).where(
            Rating.user_id == current_user.id,
            Rating.movie_id == body.movie_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ezt a filmet már értékelted. Használd a PUT végpontot a módosításhoz.",
        )

    rating = Rating(
        id=uuid.uuid4(),
        user_id=current_user.id,
        movie_id=body.movie_id,
        rating=body.rating,
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return rating


# ---------------------------------------------------------------------------
# PUT /ratings/{movie_id}  – értékelés módosítása
# ---------------------------------------------------------------------------

@router.put("/{movie_id}", response_model=RatingResponse)
def update_rating(
    movie_id: int,
    body: RatingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Rating:
    rating = db.execute(
        select(Rating).where(
            Rating.user_id == current_user.id,
            Rating.movie_id == movie_id,
        )
    ).scalar_one_or_none()

    if rating is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nem található értékelés ehhez a filmhez.",
        )

    rating.rating = body.rating
    db.commit()
    db.refresh(rating)
    return rating


# ---------------------------------------------------------------------------
# DELETE /ratings/{movie_id}  – értékelés törlése
# ---------------------------------------------------------------------------

@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rating(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    rating = db.execute(
        select(Rating).where(
            Rating.user_id == current_user.id,
            Rating.movie_id == movie_id,
        )
    ).scalar_one_or_none()

    if rating is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nem található értékelés ehhez a filmhez.",
        )

    db.delete(rating)
    db.commit()
