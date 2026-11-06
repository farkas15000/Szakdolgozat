# src/backend/app/recommender/evaluate.py
"""
Offline kiértékelő script – összehasonlítja a popularity, content-based,
SVD és hybrid ajánlókat ugyanazon rögzített train/test felosztáson.

Metrikák: Precision@K, Recall@K, NDCG@K, RMSE, MAE

Használat:
    python -m src.backend.app.recommender.evaluate
    python -m src.backend.app.recommender.evaluate --k 10 --test-ratio 0.2
    python -m src.backend.app.recommender.evaluate --ratings-csv data/ratings.csv

    # Konkrét felhasználói példák a négy módszer ajánlásának összevetésére:
    python -m src.backend.app.recommender.evaluate --example-user-ids 5,23,101
    python -m src.backend.app.recommender.evaluate --example-users-count 3

A script NEM használja az élő DB-t a train/test splithez –
a MovieLens ratings.csv-t közvetlenül olvassa, hogy az eredmény
reprodukálható és az online DB-től független legyen.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import pickle
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("evaluate")

# ---------------------------------------------------------------------------
# Alapértelmezett útvonalak – felülírhatók env változóval vagy CLI flaggel
# ---------------------------------------------------------------------------
DEFAULT_RATINGS_CSV = os.environ.get("RATINGS_CSV_PATH", "dataset/ml-latest-small/ratings.csv")
DEFAULT_GENOME_SCORES_CSV = os.environ.get("GENOME_SCORES_CSV", "dataset/ml-latest-small/genome-scores.csv")
DEFAULT_MOVIES_CSV = os.environ.get("MOVIES_CSV", "dataset/ml-latest-small/movies.csv")
SVD_MODEL_PATH = os.environ.get("SVD_MODEL_PATH", "models/svd.pkl")
CONTENT_MODEL_PATH = os.environ.get("CONTENT_MODEL_PATH", "models/content.pkl")


# ---------------------------------------------------------------------------
# Adatbetöltés
# ---------------------------------------------------------------------------

def load_ratings(csv_path: str) -> list[tuple[str, int, float]]:
    """Visszaad (user_id_str, movie_id_int, rating_float) listát."""
    import csv
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((str(row["userId"]), int(row["movieId"]), float(row["rating"])))
    logger.info(f"Betöltve: {len(rows)} értékelés, fájl: {csv_path}")
    return rows


def load_genome_scores(csv_path: str) -> dict[int, dict[int, float]]:
    """Visszaad {movie_id: {tag_id: relevance}} dict-et."""
    import csv
    if not Path(csv_path).exists():
        logger.warning(f"Genome scores fájl nem található: {csv_path} – genome nélkül folytatjuk.")
        return {}
    genome: dict[int, dict[int, float]] = defaultdict(dict)
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            genome[int(row["movieId"])][int(row["tagId"])] = float(row["relevance"])
    logger.info(f"Genome scores betöltve: {len(genome)} film")
    return dict(genome)


def load_genres(csv_path: str) -> dict[int, list[str]]:
    """Visszaad {movie_id: [genre1, genre2, ...]} dict-et."""
    import csv
    genres: dict[int, list[str]] = {}
    if not Path(csv_path).exists():
        logger.warning(f"Movies fájl nem található: {csv_path}")
        return genres
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = int(row["movieId"])
            genre_list = [g for g in row["genres"].split("|") if g != "(no genres listed)"]
            genres[mid] = genre_list
    logger.info(f"Műfajok betöltve: {len(genres)} film")
    return genres


def load_movie_titles(csv_path: str) -> dict[int, str]:
    """Visszaad {movie_id: title} dict-et – a felhasználói példák olvasható megjelenítéséhez."""
    import csv
    titles: dict[int, str] = {}
    if not Path(csv_path).exists():
        logger.warning(f"Movies fájl nem található: {csv_path}")
        return titles
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            titles[int(row["movieId"])] = row["title"]
    return titles


# ---------------------------------------------------------------------------
# Train / test split
# ---------------------------------------------------------------------------

def train_test_split(
    ratings: list[tuple[str, int, float]],
    test_ratio: float = 0.2,
    min_ratings: int = 5,
    seed: int = 42,
) -> tuple[list, list]:
    """
    Minden usernek az utolsó (időrendben legkésőbbi) test_ratio arányú
    értékelése kerül a teszt halmazba. Az adatok időrend szerint vannak
    rendezve a MovieLens CSV-ben (timestamp alapján), ezért az egyszerű
    sorrend is helyes.

    Csak azokat a usereket vonjuk be, akiknek legalább min_ratings értékelésük van.
    """
    random.seed(seed)

    # Csoportosítás userenként (megtartjuk az eredeti sorrendet)
    user_ratings: dict[str, list] = defaultdict(list)
    for uid, mid, r in ratings:
        user_ratings[uid].append((uid, mid, r))

    train, test = [], []
    for uid, user_rows in user_ratings.items():
        if len(user_rows) < min_ratings:
            train.extend(user_rows)
            continue
        n_test = max(1, int(len(user_rows) * test_ratio))
        train.extend(user_rows[:-n_test])
        test.extend(user_rows[-n_test:])

    logger.info(
        f"Split kész: {len(train)} train értékelés, {len(test)} teszt értékelés"
    )
    return train, test


# ---------------------------------------------------------------------------
# Content feature mátrix építése CSV-ből (DB nélkül)
# ---------------------------------------------------------------------------

def build_content_matrix(
    movie_ids: list[int],
    genres_map: dict[int, list[str]],
    genome_map: dict[int, dict[int, float]],
    genome_weight: float = 0.7,
) -> np.ndarray:
    all_genres = sorted({g for mid in movie_ids for g in genres_map.get(mid, [])})
    genre_index = {g: i for i, g in enumerate(all_genres)}
    all_tags = sorted({tid for mid in movie_ids for tid in genome_map.get(mid, {})})
    tag_index = {tid: i for i, tid in enumerate(all_tags)}

    n = len(movie_ids)
    n_g = len(all_genres)
    n_t = len(all_tags)
    matrix = np.zeros((n, n_g + n_t), dtype=np.float32)

    for i, mid in enumerate(movie_ids):
        for g in genres_map.get(mid, []):
            matrix[i, genre_index[g]] = 1.0
        if n_g > 0:
            norm = np.linalg.norm(matrix[i, :n_g])
            if norm > 0:
                matrix[i, :n_g] /= norm
        for tid, rel in genome_map.get(mid, {}).items():
            matrix[i, n_g + tag_index[tid]] = rel

    if n_t > 0:
        matrix[:, :n_g] *= (1.0 - genome_weight)
        matrix[:, n_g:] *= genome_weight

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


# ---------------------------------------------------------------------------
# Metrikák
# ---------------------------------------------------------------------------

def precision_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    """A releváns filmek aránya az első K ajánlás között."""
    if k <= 0:
        return 0.0
    hits = sum(1 for mid in recommended[:k] if mid in relevant)
    return hits / k

def recall_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for mid in recommended[:k] if mid in relevant)
    return hits / len(relevant)


def ndcg_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(i + 2)
        for i, mid in enumerate(recommended[:k])
        if mid in relevant
    )
    ideal_len = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_len))
    return dcg / idcg if idcg > 0 else 0.0


def rmse(predictions: list[tuple[float, float]]) -> float:
    if not predictions:
        return float("nan")
    return math.sqrt(sum((p - a) ** 2 for p, a in predictions) / len(predictions))


def mae(predictions: list[tuple[float, float]]) -> float:
    if not predictions:
        return float("nan")
    return sum(abs(p - a) for p, a in predictions) / len(predictions)


# ---------------------------------------------------------------------------
# Modellek
# ---------------------------------------------------------------------------

class PopularityRecommender:
    """A train halmazban legtöbbször értékelt filmeket ajánlja."""

    def fit(self, train: list[tuple[str, int, float]]) -> None:
        counts: dict[int, int] = defaultdict(int)
        for _, mid, _ in train:
            counts[mid] += 1
        self._ranking = sorted(counts, key=counts.get, reverse=True)  # type: ignore

    def recommend(self, rated_ids: set[int], candidates: list[int], top_n: int) -> list[int]:
        filtered = [mid for mid in self._ranking if mid in set(candidates) and mid not in rated_ids]
        return filtered[:top_n]


class ContentBasedOffline:
    """
    Közvetlen CSV-alapú content-based ajánló – nem igényel futó DB-t.
    Ha létezik a betanított content.pkl, azt tölti be, egyébként újraépíti.
    """

    def __init__(
        self,
        genres_map: dict[int, list[str]],
        genome_map: dict[int, dict[int, float]],
        model_path: str = CONTENT_MODEL_PATH,
    ) -> None:
        self._genres_map = genres_map
        self._genome_map = genome_map
        self._model_path = model_path
        self._movie_ids: list[int] = []
        self._matrix: np.ndarray | None = None
        self._idx: dict[int, int] = {}

    def fit(self, train: list[tuple[str, int, float]]) -> None:
        p = Path(self._model_path)
        if p.exists():
            logger.info(f"Content modell betöltve: {p}")
            with open(p, "rb") as f:
                data = pickle.load(f)
            self._movie_ids = data["movie_ids"]
            self._matrix = data["matrix"]
        else:
            logger.info("Content modell nem található, újraépítés CSV-ből...")
            all_mids = sorted(
                set(self._genres_map.keys()) | set(self._genome_map.keys())
            )
            self._movie_ids = all_mids
            self._matrix = build_content_matrix(
                all_mids, self._genres_map, self._genome_map
            )
        self._idx = {mid: i for i, mid in enumerate(self._movie_ids)}

    def recommend(
        self,
        liked_ids: list[int],
        rated_ids: set[int],
        candidates: list[int],
        top_n: int,
    ) -> list[int]:
        if not liked_ids or self._matrix is None:
            return []
        liked_indices = [self._idx[mid] for mid in liked_ids if mid in self._idx]
        if not liked_indices:
            return []
        profile = self._matrix[liked_indices].mean(axis=0)
        cand = [(mid, self._idx[mid]) for mid in candidates if mid in self._idx and mid not in rated_ids]
        if not cand:
            return []
        vecs = self._matrix[[i for _, i in cand]]
        scores = vecs @ profile
        ranked = sorted(zip([mid for mid, _ in cand], scores.tolist()), key=lambda x: x[1], reverse=True)
        return [mid for mid, _ in ranked[:top_n]]


class SVDOffline:
    """
    SVD kollaboratív szűrő az offline kiértékeléshez.

    Stratégia (sorrendben):
    1. Ha létezik svd.pkl ÉS a pkl-beli uid_map tartalmazza a CSV userId-ket
       (azaz MovieLens userId-kal lett tanítva), akkor a meglévő modellt
       tölti be.
    2. Egyébként a train halmazból tanít újra cornac SVD-t – ez biztosítja,
       hogy pontosan azok az user/item ID-k legyenek a modellben, amelyek
       a kiértékelési splitben is szerepelnek.

    A pkl-alapú betöltés csak akkor működik helyesen, ha a pkl-ben lévő
    uid_map kulcsai egyeznek a MovieLens CSV userId értékeivel (str formában).
    Ha a pkl a DB szekvenciális ID-ival tanult (1, 2, 3, ... != MovieLens
    userId), a modell minden usernél 0 találatot ad, ezért inkább újratanítunk.
    """

    def __init__(self, model_path: str = SVD_MODEL_PATH) -> None:
        self._model_path = model_path
        self._model = None
        self._uid_map: dict = {}
        self._iid_map: dict = {}

    def fit(self, train: list[tuple[str, int, float]]) -> None:
        # --- 1. lépés: meglévő pkl betöltési kísérlet ---
        p = Path(self._model_path)
        if p.exists():
            try:
                with open(p, "rb") as f:
                    data = pickle.load(f)
                model = data["model"]
                dataset = data["dataset"]
                uid_map = dataset.uid_map
                iid_map = dataset.iid_map
                # Ellenőrzés: a train userId-k legalább 10%-a megvan-e a pkl-ben?
                sample_uids = list({uid for uid, _, _ in train[:200]})
                matched = sum(1 for uid in sample_uids if str(uid) in uid_map)
                match_ratio = matched / len(sample_uids) if sample_uids else 0.0
                if match_ratio >= 0.5:
                    self._model = model
                    self._uid_map = uid_map
                    self._iid_map = iid_map
                    logger.info(
                        f"SVD pkl betöltve: {p}  "
                        f"(uid egyezés: {match_ratio:.0%} → újratanítás kihagyva)"
                    )
                    return
                else:
                    logger.warning(
                        f"SVD pkl uid_map nem egyezik a CSV userId-kkal "
                        f"(egyezés: {match_ratio:.0%}). Újratanítás a train halmazból..."
                    )
            except Exception as e:
                logger.warning(f"SVD pkl betöltési hiba ({e}), újratanítás...")

        # --- 2. lépés: újratanítás a train halmazból ---
        self._fit_from_train(train)

    def _fit_from_train(self, train: list[tuple[str, int, float]]) -> None:
        """Cornac SVD tanítása a megadott train adaton."""
        try:
            import cornac
            from cornac.data import Dataset
            from cornac.models import SVD as CornacSVD
        except ImportError:
            logger.error("cornac nincs telepítve. SVD kihagyva.")
            return

        uir = [(str(uid), str(mid), float(r)) for uid, mid, r in train]
        dataset = Dataset.from_uir(uir, seed=42)
        model = CornacSVD(k=100, max_iter=20, learning_rate=0.01, lambda_reg=0.02, seed=42, verbose=False)
        model.fit(dataset)
        self._model = model
        self._uid_map = dataset.uid_map
        self._iid_map = dataset.iid_map
        logger.info(
            f"SVD újratanítva: {len(self._uid_map)} user, {len(self._iid_map)} item "
            f"(train split alapján)"
        )

    def recommend(
        self,
        user_id: str,
        rated_ids: set[int],
        candidates: list[int],
        top_n: int,
    ) -> list[int]:
        if self._model is None or str(user_id) not in self._uid_map:
            return []
        uid_idx = self._uid_map[str(user_id)]
        preds = []
        for mid in candidates:
            if mid in rated_ids:
                continue
            movie_str = str(mid)
            if movie_str not in self._iid_map:
                continue
            score = self._model.score(uid_idx, self._iid_map[movie_str])
            preds.append((mid, float(score)))
        preds.sort(key=lambda x: x[1], reverse=True)
        return [mid for mid, _ in preds[:top_n]]

    def predict_rating(self, user_id: str, movie_id: int) -> float | None:
        if self._model is None or str(user_id) not in self._uid_map:
            return None
        movie_str = str(movie_id)
        if movie_str not in self._iid_map:
            return None
        return float(self._model.score(self._uid_map[str(user_id)], self._iid_map[movie_str]))


class HybridOffline:
    """SVD + Content lineáris kombinációja, popularity fallback-kel."""

    def __init__(self, svd: SVDOffline, content: ContentBasedOffline, alpha: float = 0.6) -> None:
        self._svd = svd
        self._content = content
        self._alpha = alpha

    def fit(self, train: list[tuple[str, int, float]]) -> None:
        pass  # SVD és Content már fit-elve

    def recommend(
        self,
        user_id: str,
        liked_ids: list[int],
        rated_ids: set[int],
        candidates: list[int],
        top_n: int,
        n_ratings: int,
        min_ratings_for_svd: int = 5,
    ) -> list[int]:
        use_svd = n_ratings >= min_ratings_for_svd

        svd_results = self._svd.recommend(user_id, rated_ids, candidates, len(candidates)) if use_svd else []
        if use_svd and not svd_results:
            use_svd = False

        content_results = self._content.recommend(liked_ids, rated_ids, candidates, len(candidates))

        if not svd_results and not content_results:
            return []

        svd_map: dict[int, float] = {}
        if svd_results:
            scores = [s for s in [self._svd.predict_rating(user_id, mid) for mid in [r for r in svd_results]] if s is not None]
            if scores:
                mn, mx = min(scores), max(scores)
                rng = mx - mn or 1.0
                svd_map = {mid: (self._svd.predict_rating(user_id, mid) - mn) / rng  # type: ignore
                           for mid in svd_results
                           if self._svd.predict_rating(user_id, mid) is not None}

        content_scores_raw = []
        if content_results and self._content._matrix is not None:
            liked_indices = [self._content._idx[mid] for mid in liked_ids if mid in self._content._idx]
            if liked_indices:
                profile = self._content._matrix[liked_indices].mean(axis=0)
                for mid in content_results:
                    if mid in self._content._idx:
                        content_scores_raw.append((mid, float(self._content._matrix[self._content._idx[mid]] @ profile)))
        c_scores = [s for _, s in content_scores_raw]
        if c_scores:
            c_min, c_max = min(c_scores), max(c_scores)
            c_rng = c_max - c_min or 1.0
            content_map = {mid: (s - c_min) / c_rng for mid, s in content_scores_raw}
        else:
            content_map = {}

        alpha = self._alpha if use_svd else 0.0
        all_candidates = set(svd_results) | set(content_results)
        combined = []
        for mid in all_candidates:
            if mid in rated_ids:
                continue
            score = alpha * svd_map.get(mid, 0.0) + (1.0 - alpha) * content_map.get(mid, 0.0)
            combined.append((mid, score))
        combined.sort(key=lambda x: x[1], reverse=True)
        return [mid for mid, _ in combined[:top_n]]


# ---------------------------------------------------------------------------
# Kiértékelés
# ---------------------------------------------------------------------------

def evaluate_model(
    name: str,
    recommender,
    test: list[tuple[str, int, float]],
    train_rated: dict[str, set[int]],
    train_liked: dict[str, list[int]],
    train_n_ratings: dict[str, int],
    candidate_pool: list[int],
    k: int,
    svd: SVDOffline | None = None,
) -> dict:
    precisions, recalls, ndcgs = [], [], []
    rmse_preds: list[tuple[float, float]] = []

    # Teszt: userenként csoportosítva
    user_test: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for uid, mid, r in test:
        user_test[uid].append((mid, r))

    evaluated_users = 0
    for uid, test_items in user_test.items():
        rated = train_rated.get(uid, set())
        liked = train_liked.get(uid, [])
        n_rat = train_n_ratings.get(uid, 0)

        # Relevant = teszt filmek, amelyeket 4.0+ értékkel adott
        relevant = {mid for mid, r in test_items if r >= 4.0}
        if not relevant:
            continue

        # Jelöltek = candidate pool mínusz már értékelt filmek
        candidates = [mid for mid in candidate_pool if mid not in rated]

        # Ajánlás
        if name == "Popularity":
            recs = recommender.recommend(rated, candidates, k)
        elif name == "Content-based":
            recs = recommender.recommend(liked, rated, candidates, k)
        elif name == "SVD":
            recs = recommender.recommend(uid, rated, candidates, k)
        else:  # Hybrid
            recs = recommender.recommend(uid, liked, rated, candidates, k, n_rat)

        precisions.append(precision_at_k(recs, relevant, k))
        recalls.append(recall_at_k(recs, relevant, k))
        ndcgs.append(ndcg_at_k(recs, relevant, k))

        # RMSE/MAE csak SVD-nél számolható
        if svd is not None:
            for mid, actual in test_items:
                pred = svd.predict_rating(uid, mid)
                if pred is not None:
                    rmse_preds.append((pred, actual))

        evaluated_users += 1

    result = {
        "model": name,
        "users_evaluated": evaluated_users,
        f"Precision@{k}": round(sum(precisions) / len(precisions), 4) if precisions else 0.0,
        f"Recall@{k}": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        f"NDCG@{k}": round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else 0.0,
    }
    if rmse_preds:
        result["RMSE"] = round(rmse(rmse_preds), 4)
        result["MAE"] = round(mae(rmse_preds), 4)

    return result


# ---------------------------------------------------------------------------
# Konkrét felhasználói példák (a 4 módszer ajánlásának összevetése)
# ---------------------------------------------------------------------------

def _title(movie_titles: dict[int, str], mid: int) -> str:
    return movie_titles.get(mid, f"[ismeretlen film #{mid}]")


def pick_example_user_ids(
    requested_ids: list[str] | None,
    count: int,
    user_test: dict[str, list[tuple[int, float]]],
    train_n_ratings: dict[str, int],
    seed: int,
) -> list[str]:
    """
    Ha a felhasználó explicit megadott userId-ket, azokat használjuk
    (változatlan sorrendben, de csak azokat, amelyeknek van releváns
    (≥4.0) teszt filmjük – különben nincs mit bemutatni). Egyébként
    'count' darab userId-t választunk véletlenszerűen (rögzített seeddel,
    reprodukálhatóan) azok közül, akiknek van releváns teszt filmjük és
    legalább 7 train értékelésük (hogy a bemutatás ne csak cold-start
    eseteket mutasson).
    """
    eligible = [
        uid for uid, items in user_test.items()
        if any(r >= 4.0 for _, r in items) and train_n_ratings.get(uid, 0) >= 7
    ]

    if requested_ids:
        chosen = [uid for uid in requested_ids if uid in user_test]
        missing = [uid for uid in requested_ids if uid not in user_test]
        if missing:
            logger.warning(f"A megadott userId-k közül nem található teszt adat: {missing}")
        no_relevant = [uid for uid in chosen if not any(r >= 4.0 for _, r in user_test[uid])]
        if no_relevant:
            logger.warning(
                f"A megadott userId-knek nincs releváns (≥4.0) teszt filmjük, "
                f"ezért nem jelennek meg a példákban: {no_relevant}"
            )
        return [uid for uid in chosen if uid not in no_relevant]

    if count <= 0 or not eligible:
        return []

    rng = random.Random(seed)
    return rng.sample(eligible, min(count, len(eligible)))


def print_user_examples(
    user_ids: list[str],
    movie_titles: dict[int, str],
    train_rated: dict[str, set[int]],
    train_liked: dict[str, list[int]],
    train_n_ratings: dict[str, int],
    user_test: dict[str, list[tuple[int, float]]],
    candidate_pool: list[int],
    popularity: PopularityRecommender,
    content: ContentBasedOffline,
    svd: SVDOffline,
    hybrid: HybridOffline,
    k: int,
) -> None:
    """
    Emberileg olvasható összehasonlítást nyomtat egy-egy konkrét
    felhasználóra: kedvelt (train, ≥4.0) filmek címei, majd a négy módszer
    top-K ajánlása, ★-gal jelölve, ha az ajánlott film a teszt halmazban
    ténylegesen releváns (≥4.0) volt a usernél – ez teszi láthatóvá,
    "talált"-e az adott módszer.
    """
    if not user_ids:
        logger.info("Nincs bemutatandó felhasználói példa (sem --example-user-ids, sem --example-users-count).")
        return

    for uid in user_ids:
        rated = train_rated.get(uid, set())
        liked = train_liked.get(uid, [])
        n_rat = train_n_ratings.get(uid, 0)
        test_items = user_test.get(uid, [])
        relevant = {mid for mid, r in test_items if r >= 4.0}

        candidates = [mid for mid in candidate_pool if mid not in rated]

        recs_by_model = {
            "Popularity": popularity.recommend(rated, candidates, k),
            "Content-based": content.recommend(liked, rated, candidates, k),
            "SVD": svd.recommend(uid, rated, candidates, k),
            "Hybrid": hybrid.recommend(uid, liked, rated, candidates, k, n_rat),
        }

        print("\n" + "-" * 75)
        print(f"Felhasználó #{uid}  (train értékelés: {n_rat} db, ebből kedvelt/≥4.0: {len(liked)} db)")
        print("-" * 75)

        liked_titles = [_title(movie_titles, mid) for mid in liked[:5]]
        more = f"  (+{len(liked) - 5} további)" if len(liked) > 5 else ""
        print("Kedvelt filmek (train, ≥4.0):")
        if liked_titles:
            for t in liked_titles:
                print(f"  - {t}")
            if more:
                print(more.strip())
        else:
            print("  (nincs kedvelt film a train halmazban – lásd cold-start eset)")

        print(f"\nReleváns teszt filmek (≥4.0, amit a mérés 'eltalálni valónak' tekint): {len(relevant)} db")

        print(f"\nTop-{k} ajánlás módszerenként (★ = valódi találat a teszt halmazban):")
        for model_name, recs in recs_by_model.items():
            if not recs:
                print(f"  {model_name:<14}: (üres ajánlás)")
                continue
            line_items = []
            for mid in recs:
                mark = "★" if mid in relevant else " "
                line_items.append(f"{mark}{_title(movie_titles, mid)}")
            print(f"  {model_name:<14}:")
            for item in line_items:
                print(f"      {item}")
        hits = {name: sum(1 for mid in recs if mid in relevant) for name, recs in recs_by_model.items()}
        print(f"\n  Találatok száma (top-{k}-on belül): " + ", ".join(f"{n}={c}" for n, c in hits.items()))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ajánlórendszer offline kiértékelés")
    parser.add_argument("--ratings-csv", default=DEFAULT_RATINGS_CSV)
    parser.add_argument("--genome-csv", default=DEFAULT_GENOME_SCORES_CSV)
    parser.add_argument("--movies-csv", default=DEFAULT_MOVIES_CSV)
    parser.add_argument("--k", type=int, default=10, help="Top-K (pl. 10)")
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--candidate-pool-size", type=int, default=500)
    parser.add_argument("--min-ratings", type=int, default=5, help="Min értékelés a teszt usereknek")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=None, help="Eredmény CSV mentési útvonala")
    parser.add_argument(
        "--example-user-ids",
        default=None,
        help="Vesszővel elválasztott userId lista konkrét összehasonlító példákhoz, pl. '5,23,101'",
    )
    parser.add_argument(
        "--example-users-count",
        type=int,
        default=0,
        help="Ennyi userId-t válasszon véletlenszerűen (reprodukálhatóan, --seed alapján) a példákhoz, "
             "ha --example-user-ids nincs megadva",
    )
    args = parser.parse_args()

    # --- Adatbetöltés ---
    ratings = load_ratings(args.ratings_csv)
    genres_map = load_genres(args.movies_csv)
    genome_map = load_genome_scores(args.genome_csv)
    movie_titles = load_movie_titles(args.movies_csv)

    # --- Train/test split ---
    train, test = train_test_split(
        ratings,
        test_ratio=args.test_ratio,
        min_ratings=args.min_ratings,
        seed=args.seed,
    )

    # --- Train statisztikák userenként ---
    train_rated: dict[str, set[int]] = defaultdict(set)
    train_liked: dict[str, list[int]] = defaultdict(list)
    train_n_ratings: dict[str, int] = defaultdict(int)
    for uid, mid, r in train:
        train_rated[uid].add(mid)
        train_n_ratings[uid] += 1
        if r >= 4.0:
            train_liked[uid].append(mid)

    user_test: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for uid, mid, r in test:
        user_test[uid].append((mid, r))

    # --- Jelölthalmaz: a train-ben legtöbbször értékelt filmek ---
    from collections import Counter
    movie_counts = Counter(mid for _, mid, _ in train)
    candidate_pool = [mid for mid, _ in movie_counts.most_common(args.candidate_pool_size)]
    logger.info(f"Jelölthalmaz mérete: {len(candidate_pool)}")

    # --- Modellek inicializálása és betöltése ---
    popularity = PopularityRecommender()
    popularity.fit(train)

    content = ContentBasedOffline(genres_map, genome_map)
    content.fit(train)

    svd = SVDOffline()
    svd.fit(train)

    hybrid = HybridOffline(svd, content)
    hybrid.fit(train)

    # --- Kiértékelés ---
    logger.info(f"Kiértékelés: top-{args.k}, {len(set(uid for uid, _, _ in test))} teszt user")

    results = []
    results.append(evaluate_model("Popularity", popularity, test, train_rated, train_liked, train_n_ratings, candidate_pool, args.k))
    results.append(evaluate_model("Content-based", content, test, train_rated, train_liked, train_n_ratings, candidate_pool, args.k))
    results.append(evaluate_model("SVD", svd, test, train_rated, train_liked, train_n_ratings, candidate_pool, args.k, svd=svd))
    results.append(evaluate_model("Hybrid", hybrid, test, train_rated, train_liked, train_n_ratings, candidate_pool, args.k))

    # --- Eredménytábla ---
    tablength = 75
    print("\n" + "=" * tablength)
    print(f"  Ajánlórendszer offline kiértékelés – top-{args.k}")
    print("=" * tablength)
    header = f"{'Modell':<16} {'Precision@K':>12} {'Recall@K':>10} {'NDCG@K':>10} {'RMSE':>8} {'MAE':>8} {'Users':>7}"
    print(header)
    print("-" * tablength)
    for r in results:
        rmse_val = f"{r['RMSE']:.4f}" if "RMSE" in r else "     –"
        mae_val  = f"{r['MAE']:.4f}"  if "MAE"  in r else "     –"
        print(
            f"{r['model']:<16} "
            f"{r[f'Precision@{args.k}']:>12.4f} "
            f"{r[f'Recall@{args.k}']:>10.4f} "
            f"{r[f'NDCG@{args.k}']:>10.4f} "
            f"{rmse_val:>8} "
            f"{mae_val:>8} "
            f"{r['users_evaluated']:>7}"
        )
    print("=" * tablength)

    # --- Konkrét felhasználói példák ---
    requested_ids = (
        [s.strip() for s in args.example_user_ids.split(",") if s.strip()]
        if args.example_user_ids else None
    )
    example_ids = pick_example_user_ids(
        requested_ids, args.example_users_count, user_test, train_n_ratings, args.seed
    )
    if example_ids:
        print("\n" + "=" * tablength)
        print("  Konkrét felhasználói példák – a négy módszer ajánlásának összevetése")
        print("=" * tablength)
        print_user_examples(
            example_ids, movie_titles, train_rated, train_liked, train_n_ratings,
            user_test, candidate_pool, popularity, content, svd, hybrid, args.k,
        )

    # --- Opcionális CSV mentés ---
    if args.output:
        import csv
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            fieldnames = list(results[2].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        logger.info(f"Eredmény mentve: {args.output}")


if __name__ == "__main__":
    main()
