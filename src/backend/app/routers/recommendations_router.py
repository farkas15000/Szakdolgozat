# src/backend/app/routers/recommendations.py
"""
GET /recommendations – személyre szabott ajánlások.

Logika:
1. Ha van érvényes (nem lejárt) előre számolt ajánlás → azt adja vissza.
2. Ha nincs → real-time számol a HybridRecommender-rel és elmenti.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.core.database import get_db
from src.backend.app.core.auth_dependencies import get_current_user
from src.backend.app.models.models import Movie, Recommendation, User
from src.backend.app.recommender.hybrid import EXPIRES_HOURS, recommender
from src.backend.app.schemas.recommendations_schemas import (
    RecommendationResponse,
    RecommendationsListResponse,
)
from src.backend.app.services.tmdb import get_poster_url, get_poster_urls_bulk

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GET /recommendations
# ---------------------------------------------------------------------------

@router.get("", response_model=RecommendationsListResponse)
async def get_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    top_n: int = Query(default=20, ge=1, le=100),
    refresh: bool = Query(
        default=False,
        description="Ha true, kihagyja a cache-t és újra számolja az ajánlásokat.",
    ),
) -> RecommendationsListResponse:
    user_id = str(current_user.id)
    now = datetime.now(timezone.utc)

    # --- 1. Előre számolt ajánlások keresése ---
    if not refresh:
        cached = db.execute(
            select(Recommendation)
            .where(
                Recommendation.user_id == current_user.id,
                Recommendation.expires_at > now,
            )
            .order_by(Recommendation.score.desc())
            .limit(top_n)
        ).scalars().all()

        if cached:
            logger.info(
                f"Cache hit: {len(cached)} ajánlás user {user_id[:8]}... számára."
            )
            return await _build_response(cached, db, source="precomputed")

    # --- 2. Real-time generálás ---
    logger.info(f"Real-time ajánlás generálás: user {user_id[:8]}...")

    try:
        results = recommender.recommend(user_id=user_id, db=db, top_n=top_n)
    except Exception as e:
        logger.error(f"Ajánlás generálás sikertelen: {e}", exc_info=True)
        # Fallback: üres lista helyett a leggyakrabban értékelt filmek
        results = _popularity_fallback(db, top_n)

    if not results:
        return RecommendationsListResponse(items=[], source="none", total=0)

    expires_at = now + timedelta(hours=EXPIRES_HOURS)

    # Régi lejárt ajánlások törlése
    from sqlalchemy import delete
    db.execute(
        delete(Recommendation).where(
            Recommendation.user_id == current_user.id,
            Recommendation.expires_at <= now,
        )
    )

    # Mentés DB-be
    new_recs = [
        Recommendation(
            id=uuid.uuid4(),
            user_id=current_user.id,
            movie_id=movie_id,
            score=score,
            algorithm=algorithm,
            model_version="1.0",
            expires_at=expires_at,
            was_shown=False,
            was_clicked=False,
        )
        for movie_id, score, algorithm in results
    ]
    db.add_all(new_recs)
    db.commit()
    for r in new_recs:
        db.refresh(r)

    return await _build_response(new_recs, db, source="realtime")


# ---------------------------------------------------------------------------
# POST /recommendations/{recommendation_id}/click
# Kattintás rögzítése – was_clicked = True
# ---------------------------------------------------------------------------

@router.post(
    "/{recommendation_id}/click",
    status_code=status.HTTP_204_NO_CONTENT,
)
def record_click(
    recommendation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    rec = db.execute(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if rec is not None:
        rec.was_clicked = True
        db.commit()


# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------

async def _build_response(
    recs: list[Recommendation],
    db: Session,
    source: str,
) -> RecommendationsListResponse:
    """Kiegészíti a film alapadatokkal."""
    movie_ids = [r.movie_id for r in recs]
    movies = {
        m.movie_id: m
        for m in db.execute(
            select(Movie).where(Movie.movie_id.in_(movie_ids))
        ).scalars().all()
    }

    # Poster URL-ek párhuzamos lekérése a TMDB-ből
    tmdb_ids = [m.tmdb_id for m in movies.values() if m.tmdb_id]
    poster_map: dict[str, str | None] = {}
    if tmdb_ids:
        poster_map = await get_poster_urls_bulk(tmdb_ids)

    items = []
    for rec in recs:
        movie = movies.get(rec.movie_id)
        items.append(
            RecommendationResponse(
                id=rec.id,
                movie_id=rec.movie_id,
                title=movie.title if movie else "Ismeretlen film",
                release_year=movie.release_year if movie else None,
                score=rec.score,
                algorithm=rec.algorithm,
                was_clicked=rec.was_clicked,
                poster_url=poster_map.get(movie.tmdb_id) if movie else None,
            )
        )

    return RecommendationsListResponse(
        items=items,
        source=source,
        total=len(items),
    )


def _popularity_fallback(
    db: Session, top_n: int
) -> list[tuple[int, float, str]]:
    from sqlalchemy import func
    from src.backend.app.models.models import Rating

    rows = db.execute(
        select(Rating.movie_id, func.count().label("cnt"))
        .group_by(Rating.movie_id)
        .order_by(func.count().desc())
        .limit(top_n)
    ).fetchall()

    return [(mid, float(cnt), "popularity") for mid, cnt in rows]
