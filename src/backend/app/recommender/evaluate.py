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

    Érzékenységi vizsgálat (SVD hiperparaméterek, hibrid alfa, több seed):
    python -m src.backend.app.recommender.evaluate --sweep --k 10 \
        --seeds 42,43,44 --split-mode random \
        --svd-k-list 100,50,32 --svd-iter-list 20,50,100 \
        --alphas 0.0,0.1,0.2,0.4,0.6,0.8,1.0 \
        --sweep-output-prefix /var/lib/recommender_model/data/sweep_random

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
from collections import Counter, defaultdict
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

# Az eddigi (hangolatlan) SVD-beállítás – ez az alapérték mindenhol
SVD_DEFAULT_K = 100
SVD_DEFAULT_ITER = 20
SVD_DEFAULT_LR = 0.01
SVD_DEFAULT_LAMBDA = 0.02
HYBRID_MIN_RATINGS_FOR_SVD = 5


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

    FIGYELEM: ez a felosztás determinisztikus, a seed-től NEM függ.

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


def random_user_split(
    ratings: list[tuple[str, int, float]],
    test_ratio: float = 0.2,
    min_ratings: int = 5,
    seed: int = 42,
) -> tuple[list, list]:
    """
    Seed-függő felosztás: minden (>= min_ratings értékelésű) usernél
    véletlenszerűen kiválasztott test_ratio arányú értékelés kerül a tesztbe.
    Ezzel a felosztás szórása is mérhető (a temporal split nem ad szórást).
    """
    rng = random.Random(seed)
    user_ratings: dict[str, list] = defaultdict(list)
    for uid, mid, r in ratings:
        user_ratings[uid].append((uid, mid, r))

    train, test = [], []
    for uid, user_rows in user_ratings.items():
        if len(user_rows) < min_ratings:
            train.extend(user_rows)
            continue
        n_test = max(1, int(len(user_rows) * test_ratio))
        test_idx = set(rng.sample(range(len(user_rows)), n_test))
        for i, row in enumerate(user_rows):
            (test if i in test_idx else train).append(row)

    logger.info(
        f"Random split (seed={seed}): {len(train)} train, {len(test)} teszt értékelés"
    )
    return train, test


def make_split(
    ratings: list[tuple[str, int, float]],
    split_mode: str,
    test_ratio: float,
    min_ratings: int,
    seed: int,
) -> tuple[list, list]:
    if split_mode == "random":
        return random_user_split(ratings, test_ratio, min_ratings, seed)
    return train_test_split(ratings, test_ratio, min_ratings, seed)


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

def _minmax(scored: list[tuple[int, float]]) -> dict[int, float]:
    """Min-max normalizálás [0,1]-re; üres bemenetre üres dict."""
    if not scored:
        return {}
    vals = [s for _, s in scored]
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1.0
    return {mid: (s - mn) / rng for mid, s in scored}


class PopularityRecommender:
    """A train halmazban legtöbbször értékelt filmeket ajánlja."""

    def fit(self, train: list[tuple[str, int, float]]) -> None:
        counts: dict[int, int] = defaultdict(int)
        for _, mid, _ in train:
            counts[mid] += 1
        self._ranking = sorted(counts, key=counts.get, reverse=True)  # type: ignore

    def recommend(self, rated_ids: set[int], candidates: list[int], top_n: int) -> list[int]:
        cand_set = set(candidates)
        filtered = [mid for mid in self._ranking if mid in cand_set and mid not in rated_ids]
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

    def score_candidates(
        self,
        liked_ids: list[int],
        rated_ids: set[int],
        candidates: list[int],
    ) -> list[tuple[int, float]]:
        """Pontszám szerint csökkenően rendezett (movie_id, score) lista."""
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
        return sorted(zip([mid for mid, _ in cand], scores.tolist()), key=lambda x: x[1], reverse=True)

    def recommend(
        self,
        liked_ids: list[int],
        rated_ids: set[int],
        candidates: list[int],
        top_n: int,
    ) -> list[int]:
        return [mid for mid, _ in self.score_candidates(liked_ids, rated_ids, candidates)[:top_n]]


class SVDOffline:
    """
    SVD kollaboratív szűrő az offline kiértékeléshez.

    Stratégia (sorrendben):
    1. Ha létezik svd.pkl ÉS a pkl-beli uid_map tartalmazza a CSV userId-ket
       (azaz MovieLens userId-kal lett tanítva), akkor a meglévő modellt
       tölti be (csak ha allow_pkl=True).
    2. Egyébként a train halmazból tanít újra cornac SVD-t – ez biztosítja,
       hogy pontosan azok az user/item ID-k legyenek a modellben, amelyek
       a kiértékelési splitben is szerepelnek.

    A sweep módban allow_pkl=False: minden konfiguráció mindig a train
    halmazból, a megadott hiperparaméterekkel tanul.
    """

    def __init__(
        self,
        model_path: str = SVD_MODEL_PATH,
        k: int = SVD_DEFAULT_K,
        max_iter: int = SVD_DEFAULT_ITER,
        learning_rate: float = SVD_DEFAULT_LR,
        lambda_reg: float = SVD_DEFAULT_LAMBDA,
        seed: int = 42,
        allow_pkl: bool = True,
    ) -> None:
        self._model_path = model_path
        self._k = k
        self._max_iter = max_iter
        self._lr = learning_rate
        self._lambda = lambda_reg
        self._seed = seed
        self._allow_pkl = allow_pkl
        self._model = None
        self._uid_map: dict = {}
        self._iid_map: dict = {}

    def fit(self, train: list[tuple[str, int, float]]) -> None:
        # --- 1. lépés: meglévő pkl betöltési kísérlet ---
        p = Path(self._model_path)
        if self._allow_pkl and p.exists():
            try:
                with open(p, "rb") as f:
                    data = pickle.load(f)
                model = data["model"]
                dataset = data["dataset"]
                uid_map = dataset.uid_map
                iid_map = dataset.iid_map
                # Ellenőrzés: a train userId-k legalább 50%-a megvan-e a pkl-ben?
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
            import cornac  # noqa: F401
            from cornac.data import Dataset
            from cornac.models import SVD as CornacSVD
        except ImportError:
            logger.error("cornac nincs telepítve. SVD kihagyva.")
            return

        uir = [(str(uid), str(mid), float(r)) for uid, mid, r in train]
        dataset = Dataset.from_uir(uir, seed=self._seed)
        model = CornacSVD(
            k=self._k,
            max_iter=self._max_iter,
            learning_rate=self._lr,
            lambda_reg=self._lambda,
            seed=self._seed,
            verbose=False,
        )
        model.fit(dataset)
        self._model = model
        self._uid_map = dataset.uid_map
        self._iid_map = dataset.iid_map
        logger.info(
            f"SVD újratanítva (k={self._k}, max_iter={self._max_iter}, lr={self._lr}, "
            f"λ={self._lambda}, seed={self._seed}): {len(self._uid_map)} user, "
            f"{len(self._iid_map)} item"
        )

    def score_candidates(
        self,
        user_id: str,
        rated_ids: set[int],
        candidates: list[int],
    ) -> list[tuple[int, float]]:
        """Pontszám szerint csökkenően rendezett (movie_id, score) lista."""
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
        return preds

    def recommend(
        self,
        user_id: str,
        rated_ids: set[int],
        candidates: list[int],
        top_n: int,
    ) -> list[int]:
        return [mid for mid, _ in self.score_candidates(user_id, rated_ids, candidates)[:top_n]]

    def predict_rating(self, user_id: str, movie_id: int) -> float | None:
        if self._model is None or str(user_id) not in self._uid_map:
            return None
        movie_str = str(movie_id)
        if movie_str not in self._iid_map:
            return None
        return float(self._model.score(self._uid_map[str(user_id)], self._iid_map[movie_str]))


def hybrid_combine(
    svd_map: dict[int, float],
    content_map: dict[int, float],
    rated_ids: set[int],
    alpha: float,
    top_n: int,
) -> list[int]:
    """
    Lineáris kombináció: alpha * SVD + (1 - alpha) * Content.
    FIGYELEM: az alpha az SVD súlya (alpha=0 → tiszta Content, alpha=1 → tiszta SVD).
    """
    if not svd_map and not content_map:
        return []
    ids = list(content_map.keys()) + [m for m in svd_map if m not in content_map]
    combined = []
    for mid in ids:
        if mid in rated_ids:
            continue
        combined.append((mid, alpha * svd_map.get(mid, 0.0) + (1.0 - alpha) * content_map.get(mid, 0.0)))
    combined.sort(key=lambda x: x[1], reverse=True)
    return [mid for mid, _ in combined[:top_n]]


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
        min_ratings_for_svd: int = HYBRID_MIN_RATINGS_FOR_SVD,
    ) -> list[int]:
        svd_scored = (
            self._svd.score_candidates(user_id, rated_ids, candidates)
            if n_ratings >= min_ratings_for_svd else []
        )
        use_svd = bool(svd_scored)
        content_scored = self._content.score_candidates(liked_ids, rated_ids, candidates)
        alpha = self._alpha if use_svd else 0.0
        return hybrid_combine(_minmax(svd_scored), _minmax(content_scored), rated_ids, alpha, top_n)


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
# Érzékenységi vizsgálat (sweep): SVD hiperparaméterek × hibrid alfa × seedek
# ---------------------------------------------------------------------------

def _parse_int_list(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip()]


def _parse_float_list(s: str) -> list[float]:
    return [float(x) for x in s.split(",") if x.strip()]


def _mean_std(values: list[float]) -> tuple[float, float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if not vals:
        return float("nan"), float("nan")
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
    return mean, std


def _config_sort_key(model: str, config: str):
    order = {"Popularity": 0, "Content-based": 1, "SVD": 2, "Hybrid": 3}
    return (order.get(model, 9), config)


def run_sweep(args, ratings, genres_map, genome_map) -> None:
    import csv

    k = args.k
    seeds = _parse_int_list(args.seeds)
    k_list = _parse_int_list(args.svd_k_list)
    iter_list = _parse_int_list(args.svd_iter_list)
    alphas = _parse_float_list(args.alphas)

    if args.split_mode == "temporal":
        logger.warning(
            "split-mode=temporal: a felosztás determinisztikus, a seed csak az SVD "
            "inicializálást változtatja (Popularity/Content szórása 0 lesz). "
            "A felosztás szórásához használd a --split-mode random módot."
        )

    configs = [(kk, it) for kk in k_list for it in iter_list]
    logger.info(
        f"Sweep: seedek={seeds}, split={args.split_mode}, SVD rács k×iter={configs}, alfák={alphas}"
    )

    raw_rows: list[dict] = []

    for seed in seeds:
        logger.info(f"===== Seed {seed} =====")
        train, test = make_split(ratings, args.split_mode, args.test_ratio, args.min_ratings, seed)

        train_rated: dict[str, set[int]] = defaultdict(set)
        train_liked: dict[str, list[int]] = defaultdict(list)
        train_n: dict[str, int] = defaultdict(int)
        for uid, mid, r in train:
            train_rated[uid].add(mid)
            train_n[uid] += 1
            if r >= 4.0:
                train_liked[uid].append(mid)
        user_test: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for uid, mid, r in test:
            user_test[uid].append((mid, r))

        movie_counts = Counter(mid for _, mid, _ in train)
        candidate_pool = [mid for mid, _ in movie_counts.most_common(args.candidate_pool_size)]

        popularity = PopularityRecommender()
        popularity.fit(train)
        content = ContentBasedOffline(genres_map, genome_map)
        content.fit(train)

        # Felhasználónkénti előszámítás (egyszer; minden konfiguráció újrahasznosítja)
        users = []
        for uid, items in user_test.items():
            relevant = {mid for mid, r in items if r >= 4.0}
            if not relevant:
                continue
            rated = train_rated.get(uid, set())
            liked = train_liked.get(uid, [])
            candidates = [mid for mid in candidate_pool if mid not in rated]
            content_scored = content.score_candidates(liked, rated, candidates)
            users.append({
                "uid": uid, "items": items, "relevant": relevant, "rated": rated,
                "n_rat": train_n.get(uid, 0), "candidates": candidates,
                "content_scored": content_scored, "content_map": _minmax(content_scored),
            })
        logger.info(f"Kiértékelt felhasználók: {len(users)}")

        acc: dict[tuple[str, str], dict] = defaultdict(lambda: {"P": [], "R": [], "N": [], "pairs": []})

        def record(key, recs, relevant):
            a = acc[key]
            a["P"].append(precision_at_k(recs, relevant, k))
            a["R"].append(recall_at_k(recs, relevant, k))
            a["N"].append(ndcg_at_k(recs, relevant, k))

        # Baseline-ok
        for u in users:
            record(("Popularity", "-"), popularity.recommend(u["rated"], u["candidates"], k), u["relevant"])
            record(("Content-based", "-"), [m for m, _ in u["content_scored"][:k]], u["relevant"])

        # SVD rács + hibrid alfa-sweep (minden SVD-konfigurációra)
        for kk, it in configs:
            cfg = f"k={kk},iter={it}"
            svd = SVDOffline(
                k=kk, max_iter=it, learning_rate=args.svd_lr, lambda_reg=args.svd_lambda,
                seed=seed, allow_pkl=False,
            )
            svd.fit(train)
            if svd._model is None:
                logger.error("SVD nem tanítható (cornac hiányzik?) – a konfiguráció kimarad.")
                continue
            for u in users:
                svd_scored = svd.score_candidates(u["uid"], u["rated"], u["candidates"])
                record(("SVD", cfg), [m for m, _ in svd_scored[:k]], u["relevant"])
                for m, actual in u["items"]:
                    pred = svd.predict_rating(u["uid"], m)
                    if pred is not None:
                        acc[("SVD", cfg)]["pairs"].append((pred, actual))

                use_svd = u["n_rat"] >= HYBRID_MIN_RATINGS_FOR_SVD and bool(svd_scored)
                svd_map = _minmax(svd_scored) if use_svd else {}
                for a in alphas:
                    eff = a if use_svd else 0.0
                    recs = hybrid_combine(svd_map, u["content_map"], u["rated"], eff, k)
                    record(("Hybrid", f"{cfg},alpha={a:g}"), recs, u["relevant"])
            del svd

        for (model, cfg), a in acc.items():
            row = {
                "seed": seed, "model": model, "config": cfg, "users": len(a["P"]),
                f"Precision@{k}": sum(a["P"]) / len(a["P"]),
                f"Recall@{k}": sum(a["R"]) / len(a["R"]),
                f"NDCG@{k}": sum(a["N"]) / len(a["N"]),
                "RMSE": rmse(a["pairs"]) if a["pairs"] else float("nan"),
                "MAE": mae(a["pairs"]) if a["pairs"] else float("nan"),
            }
            raw_rows.append(row)
        logger.info(f"Seed {seed} kész.")

    # --- Aggregálás seedek között ---
    metric_cols = [f"Precision@{k}", f"Recall@{k}", f"NDCG@{k}", "RMSE", "MAE"]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in raw_rows:
        groups[(r["model"], r["config"])].append(r)

    summary = []
    for (model, cfg), rs in sorted(groups.items(), key=lambda kv: _config_sort_key(*kv[0])):
        row = {"model": model, "config": cfg, "n_seeds": len(rs),
               "users_mean": round(sum(r["users"] for r in rs) / len(rs), 1)}
        for m in metric_cols:
            mean, std = _mean_std([r[m] for r in rs])
            row[f"{m}_mean"] = mean
            row[f"{m}_std"] = std
        summary.append(row)

    # --- Kiírás ---
    def fmt(row, m):
        mean, std = row[f"{m}_mean"], row[f"{m}_std"]
        return "–" if math.isnan(mean) else f"{mean:.4f}±{std:.4f}"

    width = 118
    print("\n" + "=" * width)
    print(f"  Érzékenységi vizsgálat – top-{k}, split={args.split_mode}, seedek={seeds} (átlag±szórás)")
    print("=" * width)
    print(f"{'Modell':<14} {'Konfiguráció':<30} {f'Precision@{k}':>16} {f'Recall@{k}':>16} {f'NDCG@{k}':>16} {'RMSE':>14} {'MAE':>14}")
    print("-" * width)
    for row in summary:
        print(
            f"{row['model']:<14} {row['config']:<30} "
            f"{fmt(row, f'Precision@{k}'):>16} {fmt(row, f'Recall@{k}'):>16} {fmt(row, f'NDCG@{k}'):>16} "
            f"{fmt(row, 'RMSE'):>14} {fmt(row, 'MAE'):>14}"
        )
    print("=" * width)

    # Rövid összegzés a levélben kért kérdésre
    ndcg_key = f"NDCG@{k}_mean"
    content_row = next((r for r in summary if r["model"] == "Content-based"), None)
    svd_rows = [r for r in summary if r["model"] == "SVD"]
    hyb_rows = [r for r in summary if r["model"] == "Hybrid"]
    print("\nÖsszegzés (NDCG@%d alapján, seedek átlaga):" % k)
    if content_row:
        print(f"  Content-based : {fmt(content_row, f'NDCG@{k}')}")
    if svd_rows:
        b = max(svd_rows, key=lambda r: r[ndcg_key])
        print(f"  Legjobb SVD   : {b['config']}  → {fmt(b, f'NDCG@{k}')}")
    if hyb_rows:
        b = max(hyb_rows, key=lambda r: r[ndcg_key])
        print(f"  Legjobb Hybrid: {b['config']}  → {fmt(b, f'NDCG@{k}')}")
    if content_row and (svd_rows or hyb_rows):
        best_overall = max(svd_rows + hyb_rows, key=lambda r: r[ndcg_key])
        diff = best_overall[ndcg_key] - content_row[ndcg_key]
        print(
            f"  Legjobb személyre szabott CF-es konfiguráció vs. Content-based: "
            f"{diff:+.4f} NDCG (Content szórása: {content_row[f'NDCG@{k}_std']:.4f})"
        )
    print(
        "  Megjegyzés: a konfigurációk a TESZT halmazon lettek összevetve → érzékenységi "
        "vizsgálatként közöld, ne 'a teszten kiválasztott legjobb modellként'."
    )

    # --- CSV mentés ---
    prefix = args.sweep_output_prefix
    if prefix:
        raw_path, sum_path = f"{prefix}_raw.csv", f"{prefix}_summary.csv"
        with open(raw_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(raw_rows[0].keys()))
            w.writeheader()
            w.writerows(raw_rows)
        with open(sum_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            w.writeheader()
            w.writerows(summary)
        logger.info(f"Mentve: {raw_path}, {sum_path}")


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
    # --- Érzékenységi vizsgálat ---
    parser.add_argument("--sweep", action="store_true",
                        help="Érzékenységi vizsgálat: SVD hiperparaméter-rács × hibrid alfa × több seed")
    parser.add_argument("--seeds", default="42,43,44", help="Sweep: vesszővel elválasztott seedek")
    parser.add_argument("--split-mode", choices=["temporal", "random"], default="temporal",
                        help="temporal: user-enként az időben utolsó 20%% (determinisztikus, seedtől független); "
                             "random: user-enként véletlen 20%% (seedtől függ → a felosztás szórása is mérhető)")
    parser.add_argument("--svd-k-list", default="100,50,32", help="Sweep: SVD látens dimenziók")
    parser.add_argument("--svd-iter-list", default="20,50,100", help="Sweep: SVD max_iter értékek")
    parser.add_argument("--alphas", default="0.0,0.1,0.2,0.4,0.6,0.8,1.0",
                        help="Sweep: hibrid alfa értékek (az alfa az SVD súlya!)")
    parser.add_argument("--svd-lr", type=float, default=SVD_DEFAULT_LR, help="Sweep: SVD tanulási ráta")
    parser.add_argument("--svd-lambda", type=float, default=SVD_DEFAULT_LAMBDA, help="Sweep: SVD regularizáció")
    parser.add_argument("--sweep-output-prefix", default=None,
                        help="Sweep: CSV előtag; létrejön <prefix>_raw.csv és <prefix>_summary.csv")
    args = parser.parse_args()

    # --- Adatbetöltés ---
    ratings = load_ratings(args.ratings_csv)
    genres_map = load_genres(args.movies_csv)
    genome_map = load_genome_scores(args.genome_csv)

    if args.sweep:
        run_sweep(args, ratings, genres_map, genome_map)
        return

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
