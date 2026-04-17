# src/backend/app/recommender/hybrid.py
"""
Hibrid ajánlórendszer: SVD + Content-based lineáris kombinációja.

Működés:
    score = alpha * svd_score + (1 - alpha) * content_score

    - Ha a usernek van elég értékelése (≥ MIN_RATINGS_FOR_SVD):
        SVD + Content kombinálva (alpha = SVD_WEIGHT)
    - Ha kevés az értékelés (cold start):
        Csak Content-based (alpha = 0)

Batch betanítás:
    python -m src.backend.app.recommender.train

Előre generált ajánlások:
    python -m src.backend.app.recommender.batch_generate
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Konfiguráció – .env-ből vagy alapértelmezett
SVD_MODEL_PATH = os.environ.get("SVD_MODEL_PATH", "models/svd.pkl")
CONTENT_MODEL_PATH = os.environ.get("CONTENT_MODEL_PATH", "models/content.pkl")
SVD_WEIGHT = float(os.environ.get("HYBRID_SVD_WEIGHT", "0.6"))
MIN_RATINGS_FOR_SVD = int(os.environ.get("MIN_RATINGS_FOR_SVD", "5"))
DEFAULT_TOP_N = int(os.environ.get("RECOMMENDATION_TOP_N", "20"))
CANDIDATE_POOL_SIZE = int(os.environ.get("CANDIDATE_POOL_SIZE", "500"))
EXPIRES_HOURS = int(os.environ.get("EXPIRES_HOURS", "24"))


class HybridRecommender:
    """
    Lazy-load: a modellek csak az első híváskor töltődnek be memóriába.
    Így a FastAPI worker indítása gyors marad.
    """

    _svd: object = None
    _content: object = None

    def _load_models(self) -> None:
        from src.backend.app.recommender.collaborative import SVDRecommender
        from src.backend.app.recommender.content_based import ContentRecommender

        if self._svd is None:
            svd_path = Path(SVD_MODEL_PATH)
            if svd_path.exists():
                self._svd = SVDRecommender(svd_path)
                logger.info(f"SVD modell betöltve: v{self._svd.model_version}")
            else:
                logger.warning(
                    f"SVD modell nem található: {svd_path}. "
                    "Csak content-based ajánlás lesz elérhető."
                )

        if self._content is None:
            content_path = Path(CONTENT_MODEL_PATH)
            if content_path.exists():
                self._content = ContentRecommender(content_path)
                logger.info(
                    f"Content modell betöltve: v{self._content.model_version}"
                )
            else:
                logger.warning(
                    f"Content modell nem található: {content_path}."
                )

    def recommend(
        self,
        user_id: str,
        db: Session,
        top_n: int = DEFAULT_TOP_N,
    ) -> list[tuple[int, float, str]]:
        """
        Visszaad top_n (movie_id, score, algorithm) tuple-t.
        Az 'algorithm' mező mutatja, melyik módszer adta az ajánlást.
        """
        from sqlalchemy import select, func
        from src.backend.app.models.models import Movie, Rating

        self._load_models()

        # --- User értékelései ---
        user_ratings = db.execute(
            select(Rating.movie_id, Rating.rating)
            .where(Rating.user_id == user_id)
        ).fetchall()

        rated_movie_ids = {r[0] for r in user_ratings}
        liked_movie_ids = [r[0] for r in user_ratings if r[1] >= 4.0]
        n_ratings = len(user_ratings)

        # --- Jelölt filmek: a leggyakrabban értékelt, még nem látott filmek ---
        candidate_rows = db.execute(
            select(Rating.movie_id, func.count().label("cnt"))
            .where(Rating.movie_id.not_in(rated_movie_ids))
            .group_by(Rating.movie_id)
            .order_by(func.count().desc())
            .limit(CANDIDATE_POOL_SIZE)
        ).fetchall()

        candidate_ids = [r[0] for r in candidate_rows]

        if not candidate_ids:
            # Fallback: az összes film
            candidate_ids = [
                r[0] for r in db.execute(
                    select(Movie.movie_id).limit(CANDIDATE_POOL_SIZE)
                ).fetchall()
            ]

        # --- Algoritmus kiválasztása ---
        use_svd = self._svd is not None and n_ratings >= MIN_RATINGS_FOR_SVD
        use_content = self._content is not None and len(liked_movie_ids) > 0

        if not use_svd and not use_content:
            # Hideg start + nincs modell: népszerűség alapú fallback
            logger.info(f"User {user_id}: popularity fallback")
            return [
                (mid, float(CANDIDATE_POOL_SIZE - i), "popularity")
                for i, mid in enumerate(candidate_ids[:top_n])
            ]

        # --- SVD scores ---
        svd_map: dict[int, float] = {}
        if use_svd:
            svd_results = self._svd.recommend(
                user_id, candidate_ids, top_n=len(candidate_ids)
            )
            svd_min = min(s for _, s in svd_results) if svd_results else 0.0
            svd_max = max(s for _, s in svd_results) if svd_results else 1.0
            rng = svd_max - svd_min or 1.0
            svd_map = {mid: (s - svd_min) / rng for mid, s in svd_results}

        # --- Content scores ---
        content_map: dict[int, float] = {}
        if use_content:
            content_results = self._content.recommend(
                liked_movie_ids, candidate_ids, top_n=len(candidate_ids)
            )
            c_min = min(s for _, s in content_results) if content_results else 0.0
            c_max = max(s for _, s in content_results) if content_results else 1.0
            rng = c_max - c_min or 1.0
            content_map = {
                mid: (s - c_min) / rng for mid, s in content_results
            }

        # --- Hibrid összesítés ---
        alpha = SVD_WEIGHT if use_svd else 0.0
        results: list[tuple[int, float, str]] = []

        for mid in candidate_ids:
            svd_s = svd_map.get(mid, 0.0)
            content_s = content_map.get(mid, 0.0)
            score = alpha * svd_s + (1.0 - alpha) * content_s

            if use_svd and use_content:
                algo = "hybrid"
            elif use_svd:
                algo = "svd"
            else:
                algo = "content_based"

            results.append((mid, score, algo))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]


# Singleton – FastAPI workerenként egy példány
recommender = HybridRecommender()
