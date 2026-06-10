# src/backend/app/recommender/collaborative.py
"""
SVD-alapú kollaboratív szűrés a cornac könyvtárral.
A cornac aktívan karbantartott, Python 3.12+ támogatott.

Telepítés: pip install cornac

Betanítás:
    trainer = SVDTrainer(db)
    trainer.train()
    trainer.save("models/svd.pkl")

Ajánlás:
    engine = SVDRecommender("models/svd.pkl")
    scores = engine.recommend(user_id, candidate_movie_ids, top_n=20)
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SVDTrainer:
    """Betölti az értékeléseket a DB-ből és betanítja a cornac SVD modellt."""

    MODEL_VERSION = "2.0"

    def __init__(
        self,
        db: Session,
        n_factors: int = 100,
        n_epochs: int = 20,
        lr: float = 0.01,
        reg: float = 0.02,
    ) -> None:
        self.db = db
        self.n_factors = n_factors
        self.n_epochs = n_epochs
        self.lr = lr
        self.reg = reg
        self._model = None
        self._dataset = None
        self._movie_str_list: list[str] = []

    def train(self) -> None:
        from cornac.data import Dataset
        from cornac.models import SVD

        from src.backend.app.models.models import Rating

        logger.info("SVD betanítás: értékelések betöltése...")
        rows = self.db.execute(
            select(Rating.user_id, Rating.movie_id, Rating.rating)
        ).fetchall()

        if not rows:
            raise ValueError("Nincsenek értékelések az adatbázisban.")

        uir_data = [
            ((user_id), str(movie_id), float(rating))
            for user_id, movie_id, rating in rows
        ]

        all_movies = sorted({t[1] for t in uir_data})
        self._movie_str_list = all_movies

        dataset = Dataset.from_uir(uir_data, seed=42)

        logger.info(
            f"SVD betanítás: {dataset.num_users} user, "
            f"{dataset.num_items} film, {dataset.num_ratings} értékelés."
        )

        model = SVD(
            k=self.n_factors,
            max_iter=self.n_epochs,
            learning_rate=self.lr,
            lambda_reg=self.reg,
            verbose=False,
            seed=42,
        )
        model.fit(dataset)

        self._model = model
        self._dataset = dataset
        logger.info("SVD betanítás kész.")

    def save(self, path: str | Path) -> None:
        if self._model is None:
            raise RuntimeError("Előbb hívd meg a train() metódust.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "model": self._model,
                    "dataset": self._dataset,
                    "movie_str_list": self._movie_str_list,
                    "version": self.MODEL_VERSION,
                },
                f,
            )
        logger.info(f"SVD modell mentve: {path}")


class SVDRecommender:
    """Betöltött cornac SVD modell alapján ajánlásokat generál."""

    def __init__(self, model_path: str | Path) -> None:
        with open(model_path, "rb") as f:
            data = pickle.load(f)
        self._model = data["model"]
        self._dataset = data["dataset"]
        self._movie_str_list: list[str] = data["movie_str_list"]
        self.model_version: str = data.get("version", "unknown")

    def recommend(
        self,
        user_id,
        candidate_movie_ids: list[int],
        top_n: int = 20,
    ) -> list[tuple[int, float]]:
        """
        Visszaad top_n (movie_id, score) párt csökkenő score sorrendben.
        Csak a candidate_movie_ids-ban szereplő filmeket veszi figyelembe.
        """
        uid_map = self._dataset.uid_map
        if user_id not in uid_map:
            logger.debug(f"Ismeretlen user a modellben: {user_id}...")
            return []

        iid_map = self._dataset.iid_map

        predictions: list[tuple[int, float]] = []
        for movie_id in candidate_movie_ids:
            movie_str = str(movie_id)
            if movie_str not in iid_map:
                continue
            score = self._model.score(uid_map[user_id], movie_id)
            predictions.append((movie_id, float(score)))

        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions[:top_n]
