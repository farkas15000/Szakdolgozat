"""MovieLens seed script – pandas chunksize + psycopg2 execute_batch.

Használat:
    python seed_movielens.py --data-dir /path/to/ml-latest

Szükséges csomagok:
    pip install pandas psycopg2-binary python-dotenv

Fájlok a --data-dir mappában:
    movies.csv, ratings.csv, tags.csv,
    genome-tags.csv, genome-scores.csv
"""

import argparse
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Környezet
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL nincs beállítva.")

# ---------------------------------------------------------------------------
# Batch méretek
# ---------------------------------------------------------------------------

MOVIE_BATCH        = 2_000
RATING_CHUNK       = 200_000   # pandas chunk méret ratings.csv-hez
RATING_BATCH       = 5_000     # execute_batch page_size
TAG_CHUNK          = 100_000
TAG_BATCH          = 5_000
GENOME_CHUNK       = 500_000   # genome-scores.csv nagy fájl
GENOME_BATCH       = 20_000
USER_BATCH         = 5_000

# ---------------------------------------------------------------------------
# Kapcsolat
# ---------------------------------------------------------------------------

def get_conn() -> psycopg2.extensions.connection:
    """Nyers psycopg2 kapcsolat a DATABASE_URL alapján."""
    parsed = urlparse(DATABASE_URL)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
    )


def count_rows(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]


def log(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


def parse_year(title: str):
    m = re.search(r"\((\d{4})\)\s*$", str(title))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# movies + genres + movie_genres
# ---------------------------------------------------------------------------

def seed_movies(conn, data_dir: Path) -> set[int]:
    if count_rows(conn, "movies") > 0:
        log("movies – már van adat, kihagyva.")
        with conn.cursor() as cur:
            cur.execute("SELECT movie_id FROM movies")
            return {r[0] for r in cur.fetchall()}

    path = data_dir / "movies.csv"
    log(f"movies betöltése: {path}")

    df = pd.read_csv(path, dtype={"movieId": int, "title": str, "genres": str})

    # Genres kinyerése
    genres_set: set[str] = set()
    for raw in df["genres"]:
        for g in str(raw).split("|"):
            g = g.strip()
            if g and g != "(no genres listed)":
                genres_set.add(g)

    genre_list = sorted(genres_set)
    genre_index = {g: i + 1 for i, g in enumerate(genre_list)}

    # genres insert
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            "INSERT INTO genres (genre_id, name) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            [(gid, name) for name, gid in genre_index.items()],
            page_size=MOVIE_BATCH,
        )
    conn.commit()
    log(f"  {len(genre_list)} genre betöltve.")

    # movies insert
    movie_rows = [
        (int(row.movieId), row.title.strip(), parse_year(row.title))
        for row in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            "INSERT INTO movies (movie_id, title, release_year) "
            "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            movie_rows,
            page_size=MOVIE_BATCH,
        )
    conn.commit()
    log(f"  {len(movie_rows)} film betöltve.")

    # movie_genres insert
    mg_rows: list[tuple[int, int]] = []
    for row in df.itertuples(index=False):
        mid = int(row.movieId)
        for g in str(row.genres).split("|"):
            g = g.strip()
            if g and g != "(no genres listed)":
                mg_rows.append((mid, genre_index[g]))

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            "INSERT INTO movie_genres (movie_id, genre_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            mg_rows,
            page_size=MOVIE_BATCH,
        )
    conn.commit()
    log(f"  {len(mg_rows)} film–genre kapcsolat betöltve.")

    return {int(r[0]) for r in movie_rows}


# ---------------------------------------------------------------------------
# ratings + placeholder users
# ---------------------------------------------------------------------------

def seed_ratings(conn, data_dir: Path, valid_movie_ids: set[int]) -> dict[int, str]:
    if count_rows(conn, "ratings") > 0:
        log("ratings – már van adat, kihagyva.")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT movielens_user_id, id FROM users "
                "WHERE movielens_user_id IS NOT NULL"
            )
            return {r[0]: str(r[1]) for r in cur.fetchall()}

    path = data_dir / "ratings.csv"
    log(f"ratings betöltése: {path} (nagy fájl, türelem...)")

    # 1. menet: egyedi user ID-k összegyűjtése
    ml_user_ids: set[int] = set()
    for chunk in pd.read_csv(
        path,
        dtype={"userId": int, "movieId": int, "rating": float},
        usecols=["userId", "movieId"],
        chunksize=RATING_CHUNK,
    ):
        chunk = chunk[chunk["movieId"].isin(valid_movie_ids)]
        ml_user_ids.update(chunk["userId"].tolist())

    log(f"  {len(ml_user_ids):,} egyedi MovieLens user azonosítva.")

    # Placeholder userek létrehozása
    ml_to_uuid: dict[int, str] = {uid: str(uuid.uuid4()) for uid in ml_user_ids}
    user_rows = [
        (
            ml_to_uuid[uid],
            f"ml_user_{uid}@seed.local",
            "seeded_no_login",
            f"MovieLens User {uid}",
            uid,
        )
        for uid in ml_user_ids
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            "INSERT INTO users "
            "(id, email, hashed_password, display_name, movielens_user_id) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            user_rows,
            page_size=USER_BATCH,
        )
    conn.commit()
    log(f"  {len(user_rows):,} placeholder user létrehozva.")

    # 2. menet: ratings chunk-onként betöltve
    total = 0
    for chunk in pd.read_csv(
        path,
        dtype={"userId": int, "movieId": int, "rating": float},
        usecols=["userId", "movieId", "rating"],
        chunksize=RATING_CHUNK,
    ):
        chunk = chunk[chunk["movieId"].isin(valid_movie_ids)]
        chunk = chunk[chunk["userId"].isin(ml_user_ids)]

        rows = [
            (
                str(uuid.uuid4()),
                ml_to_uuid[int(r.userId)],
                int(r.movieId),
                float(r.rating),
                int(r.userId),
            )
            for r in chunk.itertuples(index=False)
        ]

        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                "INSERT INTO ratings "
                "(id, user_id, movie_id, rating, movielens_user_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                rows,
                page_size=RATING_BATCH,
            )
        conn.commit()
        total += len(rows)

        if total % 1_000_000 == 0:
            log(f"  ... {total:,} értékelés betöltve")

    log(f"  összesen {total:,} értékelés betöltve.")
    return ml_to_uuid


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------

def seed_tags(
    conn, data_dir: Path, valid_movie_ids: set[int], ml_to_uuid: dict[int, str]
) -> None:
    if count_rows(conn, "tags") > 0:
        log("tags – már van adat, kihagyva.")
        return

    path = data_dir / "tags.csv"
    log(f"tags betöltése: {path}")

    total = 0
    valid_users = set(ml_to_uuid.keys())

    for chunk in pd.read_csv(
        path,
        dtype={"userId": int, "movieId": int, "tag": str},
        usecols=["userId", "movieId", "tag"],
        chunksize=TAG_CHUNK,
    ):
        chunk = chunk[chunk["movieId"].isin(valid_movie_ids)]
        chunk = chunk[chunk["userId"].isin(valid_users)]
        chunk = chunk[chunk["tag"].notna()]
        chunk["tag"] = chunk["tag"].str.strip()
        chunk = chunk[chunk["tag"] != ""]

        rows = [
            (
                str(uuid.uuid4()),
                ml_to_uuid[int(r.userId)],
                int(r.movieId),
                str(r.tag),
                int(r.userId),
            )
            for r in chunk.itertuples(index=False)
        ]
        if not rows:
            continue

        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                "INSERT INTO tags "
                "(id, user_id, movie_id, tag, movielens_user_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                rows,
                page_size=TAG_BATCH,
            )
        conn.commit()
        total += len(rows)

    log(f"  {total:,} tag betöltve.")


# ---------------------------------------------------------------------------
# genome-tags + genome-scores
# ---------------------------------------------------------------------------

def seed_genome(conn, data_dir: Path, valid_movie_ids: set[int]) -> None:
    # Tábla létezik-e?
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_name = 'genome_scores'"
            ")"
        )
        if not cur.fetchone()[0]:
            log("genome_scores tábla nem létezik – kihagyva.")
            return

    if count_rows(conn, "genome_scores") > 0:
        log("genome_scores – már van adat, kihagyva.")
        return

    # genome-tags
    tags_path = data_dir / "genome-tags.csv"
    log(f"genome-tags betöltése: {tags_path}")
    gt_df = pd.read_csv(tags_path, dtype={"tagId": int, "tag": str})
    gt_rows = [(int(r.tagId), str(r.tag).strip()) for r in gt_df.itertuples(index=False)]

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            "INSERT INTO genome_tags (tag_id, tag) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            gt_rows,
            page_size=2_000,
        )
    conn.commit()
    log(f"  {len(gt_rows)} genome-tag betöltve.")

    # genome-scores – streaming chunk
    scores_path = data_dir / "genome-scores.csv"
    log(f"genome-scores betöltése: {scores_path} (nagy fájl, türelem...)")

    total = 0
    for chunk in pd.read_csv(
        scores_path,
        dtype={"movieId": int, "tagId": int, "relevance": float},
        chunksize=GENOME_CHUNK,
    ):
        chunk = chunk[chunk["movieId"].isin(valid_movie_ids)]
        rows = [
            (int(r.movieId), int(r.tagId), float(r.relevance))
            for r in chunk.itertuples(index=False)
        ]
        if not rows:
            continue

        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                "INSERT INTO genome_scores (movie_id, tag_id, relevance) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                rows,
                page_size=GENOME_BATCH,
            )
        conn.commit()
        total += len(rows)

        if total % 200_000 == 0:
            log(f"  ... {total:,} genome-score betöltve")

    log(f"  összesen {total:,} genome-score betöltve.")


# ---------------------------------------------------------------------------
# Belépési pont
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="MovieLens seed script")
    parser.add_argument(
        "--data-dir",
        required=True,
        type=Path,
        help="A ml-latest mappa elérési útja",
    )
    args = parser.parse_args()

    if not args.data_dir.exists():
        sys.exit(f"ERROR: A megadott mappa nem létezik: {args.data_dir}")

    start = time.time()
    log(f"Seed megkezdve: {args.data_dir}")

    conn = get_conn()
    try:
        valid_movie_ids = seed_movies(conn, args.data_dir)
        ml_to_uuid = seed_ratings(conn, args.data_dir, valid_movie_ids)
        seed_tags(conn, args.data_dir, valid_movie_ids, ml_to_uuid)
        seed_genome(conn, args.data_dir, valid_movie_ids)
    finally:
        conn.close()

    elapsed = time.time() - start
    log(f"Seed kész! Eltelt idő: {elapsed:.1f}s")


if __name__ == "__main__":
    main()