# src/backend/app/schemas/interactions.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------

class RatingCreate(BaseModel):
    movie_id: int
    rating: float = Field(..., ge=0.5, le=5.0, description="0.5 – 5.0, fél csillag lépésben")


class RatingUpdate(BaseModel):
    rating: float = Field(..., ge=0.5, le=5.0)


class RatingResponse(BaseModel):
    id: uuid.UUID
    movie_id: int
    rating: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedRatings(BaseModel):
    items: list[RatingResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# Implicit feedback
# ---------------------------------------------------------------------------

class ImplicitFeedbackCreate(BaseModel):
    movie_id: int
    event_type: str = Field(
        ..., pattern="^(view|click|watchlist_add)$",
        description="Engedélyezett értékek: view, click, watchlist_add"
    )
    duration_seconds: int | None = Field(
        default=None, ge=0,
        description="Csak 'view' event esetén releváns"
    )
    session_id: str | None = None


class ImplicitFeedbackResponse(BaseModel):
    id: uuid.UUID
    movie_id: int
    event_type: str
    duration_seconds: int | None
    session_id: str | None
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)
