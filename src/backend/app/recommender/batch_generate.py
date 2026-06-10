# src/backend/app/recommender/batch_generate.py
"""
Batch ajánlás generálás – előre kiszámolja és DB-be menti az ajánlásokat.

Minden aktív userhez (akinek van legalább 1 értékelése) generál top-N
ajánlást és elmenti a recommendations táblába.

Használat:
    python -m src.backend.app.recommender.batch_generate
    python -m src.backend.app.recommender.batch_generate --top-n 30
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("batch_generate")

DEFAULT_TOP_N = int(os.environ.get("RECOMMENDATION_TOP_N", "20"))
EXPIRES_HOURS = int(os.environ.get("RECOMMENDATION_EXPIRES_HOURS", "24"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ajánlás generálás")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    args = parser.parse_args()

    from src.backend.app.core.database import SessionLocal
    from src.backend.app.models.models import Rating, Recommendation
    from src.backend.app.recommender.hybrid import recommender

    db = SessionLocal()
    try:
        # Aktív userek: akiknek van értékelésük
        user_ids = [
            (r[0])
            for r in db.execute(
                select(Rating.user_id).distinct()
            ).fetchall()
        ]

        logger.info(f"{len(user_ids)} user ajánlásait generáljuk...")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=EXPIRES_HOURS)

        success = 0
        failed = 0

        for i, user_id in enumerate(user_ids, 1):
            try:
                results = recommender.recommend(
                    user_id=user_id,
                    db=db,
                    top_n=args.top_n,
                )

                if not results:
                    continue

                # Régi ajánlások törlése ennek a usernek
                db.execute(
                    delete(Recommendation).where(
                        Recommendation.user_id == user_id
                    )
                )

                # Új ajánlások mentése
                recs = [
                    Recommendation(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        movie_id=movie_id,
                        score=score,
                        algorithm=algorithm,
                        model_version="1.0",
                        expires_at=expires_at,
                        was_shown=False,
                        was_clicked=False,
                    )
                    for movie_id, score, algorithm in results
                ]
                db.add_all(recs)
                db.commit()
                success += 1

                if i % 1000 == 0:
                    logger.info(f"  {i}/{len(user_ids)} user feldolgozva...")

            except Exception as e:
                #logger.warning(f"User {user_id} ajánlás sikertelen: {e}")
                db.rollback()
                failed += 1

        logger.info(
            f"Batch kész. Sikeres: {success}, sikertelen: {failed}."
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
