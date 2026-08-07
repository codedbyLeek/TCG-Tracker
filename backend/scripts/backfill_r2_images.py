"""ONe-off backfill: migrate existing card images from external CDNs to Cloudflare R2.

Usage:
    python -m script.bacfill_r2_images
"""


import logging


from sqlalchemy import select


from app.core.config import settings
from app.core.database import SessionLocal
from app.core.storage import upload_image_to_r2
from app.models import Card


logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    db = SessionLocal()
    migrated, skipped, failed = 0, 0, 0

    try:
        cards = db.scalars(select(Card)).all()

        for card in cards:
            if not card.image_url:
                skipped += 1
                continue

            if card.image_url.startswith(settings.R2_PUBLIC_URL):
                skipped += 1
                continue

            try:
                new_url = upload_image_to_r2(
                    source_url=card.image_url,
                    game=card.game,
                    external_id=card.external_id,
                )
                card.image_url = new_url
                db.commit()
                migrated += 1
            except Exception:
                logger.exception("failed to migrate to image for card %s", card.external_id)
                db.rollback()
                failed += 1
    finally:
        db.close()

    print(f"Done: {migrated} migrated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()

