"""Initial schema – MovieLens recommender

Revision ID: 0001
Revises: –
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # event_type_enum
    # ------------------------------------------------------------------
    op.execute(
        "CREATE TYPE event_type_enum AS ENUM "
        "('view', 'click', 'search', 'watchlist_add')"
    )

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("movielens_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("movielens_user_id", name="uq_users_movielens_user_id"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ------------------------------------------------------------------
    # movies
    # ------------------------------------------------------------------
    op.create_table(
        "movies",
        sa.Column("movie_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("imdb_id", sa.String(20), nullable=True),
        sa.Column("tmdb_id", sa.String(20), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_movies_title", "movies", ["title"])
    op.create_index("ix_movies_release_year", "movies", ["release_year"])

    # ------------------------------------------------------------------
    # genres
    # ------------------------------------------------------------------
    op.create_table(
        "genres",
        sa.Column(
            "genre_id", sa.Integer(), primary_key=True, autoincrement=True
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.UniqueConstraint("name", name="uq_genres_name"),
    )

    # ------------------------------------------------------------------
    # movie_genres  (many-to-many)
    # ------------------------------------------------------------------
    op.create_table(
        "movie_genres",
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.movie_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "genre_id",
            sa.Integer(),
            sa.ForeignKey("genres.genre_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ------------------------------------------------------------------
    # ratings
    # ------------------------------------------------------------------
    op.create_table(
        "ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.movie_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("movielens_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "movie_id", name="uq_ratings_user_movie"),
    )
    op.create_index("ix_ratings_user_id", "ratings", ["user_id"])
    op.create_index("ix_ratings_movie_id", "ratings", ["movie_id"])

    # ------------------------------------------------------------------
    # tags
    # ------------------------------------------------------------------
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.movie_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(255), nullable=False),
        sa.Column("movielens_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_tags_user_id", "tags", ["user_id"])
    op.create_index("ix_tags_movie_id", "tags", ["movie_id"])
    op.create_index("ix_tags_tag", "tags", ["tag"])

    # ------------------------------------------------------------------
    # implicit_feedback
    # ------------------------------------------------------------------
    op.create_table(
        "implicit_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.movie_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "view", "click", "search", "watchlist_add",
                name="event_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_implicit_feedback_user_id", "implicit_feedback", ["user_id"])
    op.create_index("ix_implicit_feedback_movie_id", "implicit_feedback", ["movie_id"])
    op.create_index(
        "ix_implicit_feedback_event_type", "implicit_feedback", ["event_type"]
    )

    # ------------------------------------------------------------------
    # recommendations
    # ------------------------------------------------------------------
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.movie_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("algorithm", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("was_shown", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("was_clicked", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])
    op.create_index(
        "ix_recommendations_user_algorithm",
        "recommendations",
        ["user_id", "algorithm"],
    )
    op.create_index(
        "ix_recommendations_generated_at", "recommendations", ["generated_at"]
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("implicit_feedback")
    op.drop_table("tags")
    op.drop_table("ratings")
    op.drop_table("movie_genres")
    op.drop_table("genres")
    op.drop_table("movies")
    op.drop_table("users")
    op.execute("DROP TYPE event_type_enum")
