# src/backend/app/schemas/recommendations.py
import uuid
from pydantic import BaseModel


class RecommendationResponse(BaseModel):
    id: uuid.UUID
    movie_id: int
    title: str
    release_year: int | None
    score: float
    algorithm: str
    was_clicked: bool
    poster_url: str | None = None


class RecommendationsListResponse(BaseModel):
    items: list[RecommendationResponse]
    source: str   # "precomputed" | "realtime" | "none"
    total: int
