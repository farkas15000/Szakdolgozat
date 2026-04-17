# src/backend/app/recommender/train.py
"""
Modell betanítás – futtatható közvetlenül vagy Docker entrypointból.

Használat:
    python -m src.backend.app.recommender.train
    python -m src.backend.app.recommender.train --model svd
    python -m src.backend.app.recommender.train --model content
    python -m src.backend.app.recommender.train --model both  (alapértelmezett)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("train")

SVD_MODEL_PATH = os.environ.get("SVD_MODEL_PATH", "models/svd.pkl")
CONTENT_MODEL_PATH = os.environ.get("CONTENT_MODEL_PATH", "models/content.pkl")


def get_db_session():
    from src.backend.app.core.database import SessionLocal
    return SessionLocal()


def train_svd(db) -> None:
    from src.backend.app.recommender.collaborative import SVDTrainer

    n_factors = int(os.environ.get("SVD_N_FACTORS", "100"))
    n_epochs = int(os.environ.get("SVD_N_EPOCHS", "20"))

    logger.info(f"SVD betanítás: n_factors={n_factors}, n_epochs={n_epochs}")
    trainer = SVDTrainer(db, n_factors=n_factors, n_epochs=n_epochs)
    trainer.train()
    trainer.save(SVD_MODEL_PATH)
    logger.info(f"SVD modell mentve: {SVD_MODEL_PATH}")


def train_content(db) -> None:
    from src.backend.app.recommender.content_based import ContentProfileBuilder

    genome_weight = float(os.environ.get("CONTENT_GENOME_WEIGHT", "0.7"))

    logger.info(f"Content profil építése: genome_weight={genome_weight}")
    builder = ContentProfileBuilder(db, genome_weight=genome_weight)
    builder.build()
    builder.save(CONTENT_MODEL_PATH)
    logger.info(f"Content modell mentve: {CONTENT_MODEL_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ajánlórendszer modell betanítás")
    parser.add_argument(
        "--model",
        choices=["svd", "content", "both"],
        default="both",
        help="Melyik modellt tanítsuk be (alapértelmezett: both)",
    )
    args = parser.parse_args()

    db = get_db_session()
    try:
        if args.model in ("svd", "both"):
            train_svd(db)
        if args.model in ("content", "both"):
            train_content(db)
    except Exception as e:
        logger.error(f"Betanítás sikertelen: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()

    logger.info("Betanítás kész!")


if __name__ == "__main__":
    main()
