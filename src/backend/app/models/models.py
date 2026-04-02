import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, enum.Enum):
    view = "view"
    click = "click"
    search = "search"
    watchlist_add = "watchlist_add"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    # Links this account to a MovieLens user for seeded ratings/tags.
    # NULL for users who registered without a seed mapping.
    movielens_user_id: Mapped[int | None] = mapped_column(
        Integer, unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    ratings: Mapped[list["Rating"]] = relationship(back_populates="user")
    tags: Mapped[list["Tag"]] = relationship(back_populates="user")
    implicit_feedback: Mapped[list["ImplicitFeedback"]] = relationship(
        back_populates="user"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="user"
    )


# ---------------------------------------------------------------------------
# Movies & Genres
# ---------------------------------------------------------------------------

class Movie(Base):
    __tablename__ = "movies"

    movie_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tmdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    genres: Mapped[list["Genre"]] = relationship(
        secondary="movie_genres", back_populates="movies"
    )
    ratings: Mapped[list["Rating"]] = relationship(back_populates="movie")
    tags: Mapped[list["Tag"]] = relationship(back_populates="movie")
    implicit_feedback: Mapped[list["ImplicitFeedback"]] = relationship(
        back_populates="movie"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="movie"
    )


class Genre(Base):
    __tablename__ = "genres"

    genre_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    movies: Mapped[list["Movie"]] = relationship(
        secondary="movie_genres", back_populates="genres"
    )


class MovieGenre(Base):
    """Association table between movies and genres."""

    __tablename__ = "movie_genres"
    __table_args__ = (UniqueConstraint("movie_id", "genre_id"),)

    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.movie_id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("genres.genre_id", ondelete="CASCADE"), primary_key=True
    )


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------

class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("user_id", "movie_id"),)

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.movie_id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    # Preserved from the MovieLens CSV; NULL for ratings by new users.
    movielens_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="ratings")
    movie: Mapped["Movie"] = relationship(back_populates="ratings")


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.movie_id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(255), nullable=False)
    movielens_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="tags")
    movie: Mapped["Movie"] = relationship(back_populates="tags")


# ---------------------------------------------------------------------------
# Implicit feedback
# ---------------------------------------------------------------------------

class ImplicitFeedback(Base):
    __tablename__ = "implicit_feedback"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.movie_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type_enum"), nullable=False
    )
    # Only populated for "view" events; NULL otherwise.
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="implicit_feedback")
    movie: Mapped["Movie"] = relationship(back_populates="implicit_feedback")


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.movie_id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # e.g. "svd", "als", "content_based" — hasznos az algoritmusok összehasonlításához
    algorithm: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    was_shown: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    was_clicked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="recommendations")
    movie: Mapped["Movie"] = relationship(back_populates="recommendations")
