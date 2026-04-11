"""Add genome_tags and genome_scores tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # genome_tags  – a 1128 tag neve és ID-ja
    # ------------------------------------------------------------------
    op.create_table(
        "genome_tags",
        sa.Column("tag_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("tag", sa.String(255), nullable=False),
        sa.UniqueConstraint("tag", name="uq_genome_tags_tag"),
    )

    # ------------------------------------------------------------------
    # genome_scores  – film × tag relevancia értékek
    # ~15 millió sor, ezért:
    #   - összetett PK (movie_id, tag_id) → nincs külön UUID overhead
    #   - tag_id indexelve → tag alapú lekérdezésekhez
    # ------------------------------------------------------------------
    op.create_table(
        "genome_scores",
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.movie_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("genome_tags.tag_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("relevance", sa.Float(), nullable=False),
    )
    op.create_index("ix_genome_scores_tag_id", "genome_scores", ["tag_id"])
    op.create_index(
        "ix_genome_scores_movie_relevance",
        "genome_scores",
        ["movie_id", "relevance"],
    )


def downgrade() -> None:
    op.drop_table("genome_scores")
    op.drop_table("genome_tags")
