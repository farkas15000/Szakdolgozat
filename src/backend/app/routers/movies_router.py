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
from src.backend.app.services.tmdb import get_poster_url, get_poster_urls_bulk

router = APIRouter(prefix="/movies", tags=["movies"])


# ---------------------------------------------------------------------------
# GET /movies
# Listázás lapozással + opcionális szűrők: title, genre, year_from, year_to
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedMovies)
async def list_movies(
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

    total: int = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()

    movies = db.execute(
        query.order_by(Movie.title)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    # Poster URL-ek párhuzamos lekérése a TMDB-ből
    tmdb_ids = [m.tmdb_id for m in movies if m.tmdb_id]
    poster_map: dict[str, str | None] = {}
    if tmdb_ids:
        poster_map = await get_poster_urls_bulk(tmdb_ids)

    items = [
        MovieSummary(
            movie_id=m.movie_id,
            title=m.title,
            release_year=m.release_year,
            genres=[g.name for g in m.genres],
            poster_url=poster_map.get(m.tmdb_id) if m.tmdb_id else None,
        )
        for m in movies
    ]

    return PaginatedMovies(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


# ---------------------------------------------------------------------------
# GET /movies/genres
# ---------------------------------------------------------------------------

@router.get("/genres", response_model=list[str])
def list_genres(db: Session = Depends(get_db)) -> list[str]:
    genres = db.execute(
        select(Genre.name).order_by(Genre.name)
    ).scalars().all()
    return list(genres)


# ---------------------------------------------------------------------------
# GET /movies/{movie_id}
# ---------------------------------------------------------------------------

@router.get("/{movie_id}", response_model=MovieDetail)
async def get_movie(movie_id: int, db: Session = Depends(get_db)) -> MovieDetail:
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

    poster_url = None
    if movie.tmdb_id:
        poster_url = await get_poster_url(movie.tmdb_id)

    return MovieDetail(
        movie_id=movie.movie_id,
        title=movie.title,
        release_year=movie.release_year,
        imdb_id=movie.imdb_id,
        tmdb_id=movie.tmdb_id,
        genres=list(movie.genres),
        poster_url=poster_url,
    )
