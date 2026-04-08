"""MovieLens seed script – batch insert, idempotent.

Használat:
    python seed_movielens.py --data-dir /path/to/ml-latest

A script a következő fájlokat várja a --data-dir mappában:
    movies.csv, ratings.csv, tags.csv,
    genome-tags.csv, genome-scores.csv

Futtatás előtt győződj meg róla, hogy a DATABASE_URL környezeti
változó be van állítva (vagy a .env fájl elérhető).
"""

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import Table as sa_table, column as sa_column, MetaData


# ---------------------------------------------------------------------------
# Környezet betöltése
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL nincs beállítva.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
metadata = MetaData()

# ---------------------------------------------------------------------------
# Konstansok
# ---------------------------------------------------------------------------

MOVIE_BATCH   = 2_000
RATING_BATCH  = 10_000
TAG_BATCH     = 5_000
GENOME_BATCH  = 20_000   # genome-scores sok sor → nagy batch

# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------

def count_rows(table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def log(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


def parse_year(title: str):
    """Kivonja az évet a film címéből, pl. 'Toy Story (1995)' → 1995."""
    m = re.search(r"\((\d{4})\)\s*$", title)
    return int(m.group(1)) if m else None


def chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]

# ---------------------------------------------------------------------------
# Segéd: táblanévből SQLAlchemy Table objektum (reflection nélkül)
# ---------------------------------------------------------------------------

def text_table(name: str):
    """Minimális Table proxy az insert dialektushoz."""
    return sa_table(name, metadata, autoload_with=engine)


# ---------------------------------------------------------------------------
# Seed függvények
# ---------------------------------------------------------------------------

def seed_movies(data_dir: Path) -> dict[int, int]:
    """
    Betölti a movies.csv-t.
    Visszaad egy {movielens_movie_id: movie_id} dict-et (itt 1:1, de
    explicit visszaadjuk a konzisztencia kedvéért).
    """
    if count_rows("movies") > 0:
        log("movies – már van adat, kihagyva.")
        # Visszaadjuk a meglévő ID-kat a többi tábla seed-jéhez.
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT movie_id FROM movies")).fetchall()
        return {r[0]: r[0] for r in rows}

    path = data_dir / "movies.csv"
    log(f"movies betöltése: {path}")

    genres_seen: dict[str, int] = {}   # name → genre_id
    movie_rows: list[dict] = []
    movie_genre_rows: list[dict] = []

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            movie_id  = int(row["movieId"])
            title     = row["title"].strip()
            year      = parse_year(title)
            raw_genres = [g.strip() for g in row["genres"].split("|")
                          if g.strip() and g.strip() != "(no genres listed)"]

            movie_rows.append({
                "movie_id":    movie_id,
                "title":       title,
                "release_year": year,
            })

            for genre_name in raw_genres:
                if genre_name not in genres_seen:
                    genres_seen[genre_name] = len(genres_seen) + 1
                movie_genre_rows.append({
                    "movie_id":  movie_id,
                    "genre_id":  genres_seen[genre_name],
                })

    # genres
    genre_rows = [{"genre_id": gid, "name": name}
                  for name, gid in genres_seen.items()]
    with engine.begin() as conn:
        conn.execute(
            pg_insert(text_table("genres")).on_conflict_do_nothing(),
            genre_rows,
        )
    log(f"  {len(genre_rows)} genre betöltve.")

    # movies – batch
    total = 0
    with engine.begin() as conn:
        for batch in chunks(movie_rows, MOVIE_BATCH):
            conn.execute(
                pg_insert(text_table("movies")).on_conflict_do_nothing(),
                batch,
            )
            total += len(batch)
    log(f"  {total} film betöltve.")

    # movie_genres – batch
    total = 0
    with engine.begin() as conn:
        for batch in chunks(movie_genre_rows, MOVIE_BATCH):
            conn.execute(
                pg_insert(text_table("movie_genres")).on_conflict_do_nothing(),
                batch,
            )
            total += len(batch)
    log(f"  {total} film–genre kapcsolat betöltve.")

    return {r["movie_id"]: r["movie_id"] for r in movie_rows}


def seed_ratings(data_dir: Path, valid_movie_ids: set[int]) -> dict[int, str]:
    """
    Betölti a ratings.csv-t.
    Minden MovieLens userId-hoz létrehoz egy user rekordot (display_name csak
    placeholder, auth nélkül), és visszaadja a {ml_user_id: uuid} map-et.
    """
    if count_rows("ratings") > 0:
        log("ratings – már van adat, kihagyva.")
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT movielens_user_id, id FROM users "
                     "WHERE movielens_user_id IS NOT NULL")
            ).fetchall()
        return {r[0]: str(r[1]) for r in rows}

    path = data_dir / "ratings.csv"
    log(f"ratings betöltése: {path} (nagy fájl, türelem...)")

    # Gyűjtsük össze az egyedi userId-kat és az összes értékelést egy menetben
    ml_user_ids: set[int] = set()
    rating_rows_raw: list[tuple] = []   # (userId, movieId, rating)

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = int(row["userId"])
            mid = int(row["movieId"])
            if mid not in valid_movie_ids:
                continue
            ml_user_ids.add(uid)
            rating_rows_raw.append((uid, mid, float(row["rating"])))

    log(f"  {len(ml_user_ids)} egyedi MovieLens user, "
        f"{len(rating_rows_raw)} értékelés.")

    # Users létrehozása – minden ML user kap egy placeholder fiókot
    import uuid as uuid_module
    ml_to_uuid: dict[int, str] = {}
    user_rows: list[dict] = []
    for ml_uid in ml_user_ids:
        new_uuid = str(uuid_module.uuid4())
        ml_to_uuid[ml_uid] = new_uuid
        user_rows.append({
            "id":                new_uuid,
            "email":             f"ml_user_{ml_uid}@seed.local",
            "hashed_password":   "seeded_no_login",
            "display_name":      f"MovieLens User {ml_uid}",
            "movielens_user_id": ml_uid,
        })

    with engine.begin() as conn:
        for batch in chunks(user_rows, 2_000):
            conn.execute(
                pg_insert(text_table("users")).on_conflict_do_nothing(),
                batch,
            )
    log(f"  {len(user_rows)} user placeholder létrehozva.")

    # Ratings batch insert
    rating_rows: list[dict] = []
    for ml_uid, mid, rating in rating_rows_raw:
        rating_rows.append({
            "id":                str(uuid_module.uuid4()),
            "user_id":           ml_to_uuid[ml_uid],
            "movie_id":          mid,
            "rating":            rating,
            "movielens_user_id": ml_uid,
        })

    total = 0
    with engine.begin() as conn:
        for batch in chunks(rating_rows, RATING_BATCH):
            conn.execute(
                pg_insert(text_table("ratings")).on_conflict_do_nothing(),
                batch,
            )
            total += len(batch)
            if total % 500_000 == 0:
                log(f"  ... {total:,} értékelés betöltve")

    log(f"  összesen {total:,} értékelés betöltve.")
    return ml_to_uuid


def seed_tags(data_dir: Path,
              valid_movie_ids: set[int],
              ml_to_uuid: dict[int, str]) -> None:
    if count_rows("tags") > 0:
        log("tags – már van adat, kihagyva.")
        return

    path = data_dir / "tags.csv"
    log(f"tags betöltése: {path}")

    import uuid as uuid_module
    tag_rows: list[dict] = []

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ml_uid = int(row["userId"])
            mid    = int(row["movieId"])
            tag    = row["tag"].strip()
            if mid not in valid_movie_ids or ml_uid not in ml_to_uuid or not tag:
                continue
            tag_rows.append({
                "id":                str(uuid_module.uuid4()),
                "user_id":           ml_to_uuid[ml_uid],
                "movie_id":          mid,
                "tag":               tag,
                "movielens_user_id": ml_uid,
            })

    total = 0
    with engine.begin() as conn:
        for batch in chunks(tag_rows, TAG_BATCH):
            conn.execute(
                pg_insert(text_table("tags")).on_conflict_do_nothing(),
                batch,
            )
            total += len(batch)

    log(f"  {total:,} tag betöltve.")


def seed_genome(data_dir: Path, valid_movie_ids: set[int]) -> None:
    """
    genome-tags.csv + genome-scores.csv betöltése.
    A genome_scores táblát külön kell létrehozni (nem része az alap sémának),
    ezért ez a függvény ellenőrzi, hogy létezik-e a tábla.
    """
    # Ellenőrzés: létezik-e a genome_scores tábla?
    with engine.connect() as conn:
        exists = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'genome_scores')"
        )).scalar()

    if not exists:
        log("genome_scores tábla nem létezik – kihagyva. "
            "(Hozd létre Alembic migrációval, ha kell.)")
        return

    if count_rows("genome_scores") > 0:
        log("genome_scores – már van adat, kihagyva.")
        return

    # genome-tags.csv → genome_tags tábla
    tags_path = data_dir / "genome-tags.csv"
    log(f"genome-tags betöltése: {tags_path}")
    genome_tag_rows: list[dict] = []
    with open(tags_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            genome_tag_rows.append({
                "tag_id": int(row["tagId"]),
                "tag":    row["tag"].strip(),
            })

    with engine.begin() as conn:
        for batch in chunks(genome_tag_rows, 2_000):
            conn.execute(
                pg_insert(text_table("genome_tags")).on_conflict_do_nothing(),
                batch,
            )
    log(f"  {len(genome_tag_rows)} genome-tag betöltve.")

    # genome-scores.csv – nagy fájl, streaming olvasás
    scores_path = data_dir / "genome-scores.csv"
    log(f"genome-scores betöltése: {scores_path} (nagy fájl, türelem...)")

    total = 0
    batch: list[dict] = []

    with open(scores_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        with engine.begin() as conn:
            for row in reader:
                mid = int(row["movieId"])
                if mid not in valid_movie_ids:
                    continue
                batch.append({
                    "movie_id":   mid,
                    "tag_id":     int(row["tagId"]),
                    "relevance":  float(row["relevance"]),
                })
                if len(batch) >= GENOME_BATCH:
                    conn.execute(
                        pg_insert(text_table("genome_scores"))
                        .on_conflict_do_nothing(),
                        batch,
                    )
                    total += len(batch)
                    batch = []
                    if total % 1_000_000 == 0:
                        log(f"  ... {total:,} genome-score betöltve")
            if batch:
                conn.execute(
                    pg_insert(text_table("genome_scores"))
                    .on_conflict_do_nothing(),
                    batch,
                )
                total += len(batch)

    log(f"  összesen {total:,} genome-score betöltve.")


# ---------------------------------------------------------------------------
# Belépési pont
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MovieLens seed script")
    parser.add_argument(
        "--data-dir",
        required=True,
        type=Path,
        help="A ml-latest mappa elérési útja (ahol a CSV-k vannak)",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    print("Data path:")
    print(data_dir)

    if not data_dir.exists():
        sys.exit(f"ERROR: A megadott mappa nem létezik: {data_dir}")

    start = time.time()
    log(f"Seed megkezdve: {data_dir}")

    # 1. Filmek + genre-ok
    movie_id_map = seed_movies(data_dir)
    valid_movie_ids = set(movie_id_map.keys())

    # 2. Értékelések + placeholder userek
    ml_to_uuid = seed_ratings(data_dir, valid_movie_ids)

    # 3. Tagek
    seed_tags(data_dir, valid_movie_ids, ml_to_uuid)

    # 4. Genome (opcionális – csak ha létezik a tábla)
    seed_genome(data_dir, valid_movie_ids)

    elapsed = time.time() - start
    log(f"Seed kész! Eltelt idő: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
