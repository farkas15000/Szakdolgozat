# src/backend/app/routers/movies.py
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.backend.app.core.database import get_db
from src.backend.app.models.models import Genre, Movie, MovieGenre
from src.backend.app.schemas.movies_schemas import (
    MovieDetail,
    MovieSummary,
    PaginatedMovies,
)

router = APIRouter(prefix="/movies", tags=["movies"])

# ---------------------------------------------------------------------------
# Segéd: Movie → MovieSummary (genre nevek listája)
# ---------------------------------------------------------------------------

def _to_summary(movie: Movie) -> MovieSummary:
    return MovieSummary(
        movie_id=movie.movie_id,
        title=movie.title,
        release_year=movie.release_year,
        genres=[g.name for g in movie.genres],
    )


# ---------------------------------------------------------------------------
# GET /movies
# Listázás lapozással + opcionális szűrők: title, genre, year_from, year_to
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedMovies)
def list_movies(
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1, description="Oldalszám (1-től)")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Elemek száma oldalanként")
    ] = 20,
    title: Annotated[
        str | None, Query(description="Cím részleges egyezés (case-insensitive)")
    ] = None,
    genre: Annotated[
        str | None, Query(description="Műfaj neve (pl. Action)")
    ] = None,
    year_from: Annotated[
        int | None, Query(ge=1888, description="Megjelenési év (tól)")
    ] = None,
    year_to: Annotated[
        int | None, Query(ge=1888, description="Megjelenési év (ig)")
    ] = None,
) -> PaginatedMovies:
    query = select(Movie).options(selectinload(Movie.genres))

    # --- Szűrők ---
    if title:
        query = query.where(Movie.title.ilike(f"%{title}%"))

    if genre:
        # JOIN csak akkor, ha műfajra szűrünk
        query = (
            query
            .join(MovieGenre, Movie.movie_id == MovieGenre.movie_id)
            .join(Genre, MovieGenre.genre_id == Genre.genre_id)
            .where(Genre.name.ilike(genre))
        )

    if year_from is not None:
        query = query.where(Movie.release_year >= year_from)

    if year_to is not None:
        query = query.where(Movie.release_year <= year_to)

    # --- Összes találat száma ---
    count_query = select(func.count()).select_from(query.subquery())
    total: int = db.execute(count_query).scalar_one()

    # --- Lapozás ---
    offset = (page - 1) * page_size
    movies = db.execute(
        query.order_by(Movie.title).offset(offset).limit(page_size)
    ).scalars().all()

    return PaginatedMovies(
        items=[_to_summary(m) for m in movies],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


# ---------------------------------------------------------------------------
# GET /movies/genres
# Az összes elérhető műfaj listája (szűrő feltöltéséhez)
# ---------------------------------------------------------------------------

@router.get("/genres", response_model=list[str])
def list_genres(db: Session = Depends(get_db)) -> list[str]:
    genres = db.execute(
        select(Genre.name).order_by(Genre.name)
    ).scalars().all()
    return list(genres)


# ---------------------------------------------------------------------------
# GET /movies/{movie_id}
# Egy film részletes adatai
# ---------------------------------------------------------------------------

@router.get("/{movie_id}", response_model=MovieDetail)
def get_movie(movie_id: int, db: Session = Depends(get_db)) -> MovieDetail:
    movie = db.execute(
        select(Movie)
        .options(selectinload(Movie.genres))
        .where(Movie.movie_id == movie_id)
    ).scalar_one_or_none()

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"A(z) {movie_id} azonosítójú film nem található.",
        )

    return MovieDetail(
        movie_id=movie.movie_id,
        title=movie.title,
        release_year=movie.release_year,
        imdb_id=movie.imdb_id,
        tmdb_id=movie.tmdb_id,
        genres=[g for g in movie.genres],
    )
