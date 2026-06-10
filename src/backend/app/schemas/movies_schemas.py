# src/backend/app/schemas/movies.py
from pydantic import BaseModel, ConfigDict


class GenreResponse(BaseModel):
    genre_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class MovieSummary(BaseModel):
    """Listanézet – könnyű, genre nevek stringként, poster URL-lel."""
    movie_id:     int
    title:        str
    release_year: int | None
    genres:       list[str]
    poster_url:   str | None = None

    model_config = ConfigDict(from_attributes=True)


class MovieDetail(BaseModel):
    """Részletes nézet – genre objektumokkal és poster URL-lel."""
    movie_id:     int
    title:        str
    release_year: int | None
    imdb_id:      str | None
    tmdb_id:      str | None
    genres:       list[GenreResponse]
    poster_url:   str | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedMovies(BaseModel):
    items:     list[MovieSummary]
    total:     int
    page:      int
    page_size: int
    pages:     int
