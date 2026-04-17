# src/backend/app/recommender/content_based.py
"""
Tartalomalapú szűrés műfaj- és genome-tag vektorok alapján.

A cosine similarity alapján megkeresi azokat a filmeket,
amelyek leginkább hasonlítanak a user által magasra értékelt filmekhez.

Betanítás:
    builder = ContentProfileBuilder(db)
    builder.build()
    builder.save("models/content.pkl")

Ajánlás:
    engine = ContentRecommender("models/content.pkl")
    scores = engine.recommend(liked_movie_ids, candidate_movie_ids, top_n=20)
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ContentProfileBuilder:
    """Felépíti a film feature mátrixot műfajokból + genome score-okból."""

    MODEL_VERSION = "1.0"

    def __init__(self, db: Session, genome_weight: float = 0.7) -> None:
        self.db = db
        self.genome_weight = genome_weight  # genome vs genre arány
        self._movie_ids: list[int] = []
        self._matrix: np.ndarray | None = None

    def build(self) -> None:
        from src.backend.app.models.models import Genre, GenomeScore, Movie, MovieGenre

        logger.info("Content-based profil építése...")

        # --- Műfajok one-hot vektora ---
        genre_rows = self.db.execute(
            select(MovieGenre.movie_id, Genre.name)
            .join(Genre, MovieGenre.genre_id == Genre.genre_id)
            .order_by(MovieGenre.movie_id)
        ).fetchall()

        all_genres = sorted({r[1] for r in genre_rows})
        genre_index = {g: i for i, g in enumerate(all_genres)}

        movie_genres: dict[int, list[str]] = {}
        for mid, gname in genre_rows:
            movie_genres.setdefault(mid, []).append(gname)

        # --- Genome score-ok (ha léteznek) ---
        genome_rows = self.db.execute(
            select(GenomeScore.movie_id, GenomeScore.tag_id, GenomeScore.relevance)
        ).fetchall()
        has_genome = len(genome_rows) > 0

        all_tag_ids: list[int] = []
        movie_genome: dict[int, dict[int, float]] = {}
        if has_genome:
            all_tag_ids = sorted({r[1] for r in genome_rows})
            tag_index = {tid: i for i, tid in enumerate(all_tag_ids)}
            for mid, tid, rel in genome_rows:
                movie_genome.setdefault(mid, {})[tag_index[tid]] = rel

        # --- Összesített filmek ---
        all_movie_ids = sorted(
            set(movie_genres.keys()) | set(movie_genome.keys())
        )
        n_movies = len(all_movie_ids)
        n_genres = len(all_genres)
        n_tags = len(all_tag_ids)

        logger.info(
            f"  {n_movies} film, {n_genres} műfaj, {n_tags} genome-tag."
        )

        # --- Feature mátrix összerakása ---
        genre_dim = n_genres
        genome_dim = n_tags
        total_dim = genre_dim + genome_dim

        matrix = np.zeros((n_movies, total_dim), dtype=np.float32)

        for i, mid in enumerate(all_movie_ids):
            # Műfaj one-hot (normalizált)
            genres = movie_genres.get(mid, [])
            if genres:
                for g in genres:
                    matrix[i, genre_index[g]] = 1.0
                genre_vec = matrix[i, :genre_dim]
                norm = np.linalg.norm(genre_vec)
                if norm > 0:
                    matrix[i, :genre_dim] = genre_vec / norm

            # Genome score vektor
            if has_genome and mid in movie_genome:
                for tag_i, rel in movie_genome[mid].items():
                    matrix[i, genre_dim + tag_i] = rel

        # Súlyozás: genre vs genome
        if has_genome and n_tags > 0:
            matrix[:, :genre_dim] *= (1.0 - self.genome_weight)
            matrix[:, genre_dim:] *= self.genome_weight

        # L2 normalizálás (cosine similarity előkészítés)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms

        self._movie_ids = all_movie_ids
        self._matrix = matrix
        logger.info("Content-based profil kész.")

    def save(self, path: str | Path) -> None:
        if self._matrix is None:
            raise RuntimeError("Előbb hívd meg a build() metódust.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "movie_ids": self._movie_ids,
                    "matrix": self._matrix,
                    "version": self.MODEL_VERSION,
                },
                f,
            )
        logger.info(f"Content modell mentve: {path}")


class ContentRecommender:
    """Betöltött content modell alapján cosine similarity ajánlás."""

    def __init__(self, model_path: str | Path) -> None:
        with open(model_path, "rb") as f:
            data = pickle.load(f)
        self._movie_ids: list[int] = data["movie_ids"]
        self._matrix: np.ndarray = data["matrix"]
        self.model_version: str = data.get("version", "unknown")
        # Gyors index: movie_id → sor index
        self._idx: dict[int, int] = {
            mid: i for i, mid in enumerate(self._movie_ids)
        }

    def recommend(
        self,
        liked_movie_ids: list[int],
        candidate_movie_ids: list[int],
        top_n: int = 20,
    ) -> list[tuple[int, float]]:
        """
        liked_movie_ids: filmek, amiket a user magasra értékelt (≥ 4.0)
        candidate_movie_ids: filmek, amelyek közül ajánlunk
        Visszaad top_n (movie_id, score) párt csökkenő sorrendben.
        """
        if not liked_movie_ids:
            return []

        # User profil = a kedvelt filmek vektorainak átlaga
        liked_indices = [
            self._idx[mid] for mid in liked_movie_ids if mid in self._idx
        ]
        if not liked_indices:
            return []

        user_profile = self._matrix[liked_indices].mean(axis=0)

        # Cosine similarity a jelöltek ellen
        candidate_indices = [
            (mid, self._idx[mid])
            for mid in candidate_movie_ids
            if mid in self._idx and mid not in liked_movie_ids
        ]
        if not candidate_indices:
            return []

        candidate_vecs = self._matrix[[idx for _, idx in candidate_indices]]
        scores = candidate_vecs @ user_profile  # már normalizált → cosine

        results = [
            (mid, float(scores[i]))
            for i, (mid, _) in enumerate(candidate_indices)
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]
