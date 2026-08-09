"""Sync One Piece cards and prices from the OPTCG API (optcgapi.com)."""

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Card, Price
from app.core.storage import upload_image_to_r2

logger = logging.getLogger(__name__)

BASE_URL = "https://optcgapi.com/api"


def list_set_ids() -> list[str]:
    """Fetch every main-set ID (OP/EB/PRB) from optcgapi."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.get("/allSets/")
        response.raise_for_status()
        sets = response.json()

    return [s["set_id"] for s in sets]


def sync_set(db: Session, set_id: str) -> tuple[int, int]:
    """Sync all cards (and print variants) in one set. Returns (created, updated)."""
    created, updated = 0, 0
    now = datetime.now(timezone.utc)

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.get(f"/sets/{set_id}/")
        response.raise_for_status()
        api_cards = response.json()

    for api_card in api_cards:
        market = api_card.get("market_price")
        market_price = Decimal(str(market)) if market is not None else None

        external_id = api_card["card_image_id"]

        card = db.scalar(
            select(Card).where(Card.external_id == external_id)
        )

        if card is None:
            source_image_url = api_card.get("card_image")
            image_url = source_image_url

            if source_image_url is not None:
                try:
                    image_url = upload_image_to_r2(
                        source_url=source_image_url,
                        game="one_piece",
                        external_id=external_id,
                    )
                except Exception:
                    logger.warning(
                        "Failed to upload image to R2 for card %s, using source URL instead",
                        external_id,
                        exc_info=True,
                    )

            card = Card(
                external_id=external_id,
                name=api_card["card_name"],
                set_name=api_card.get("set_name"),
                card_number=api_card.get("card_set_id"),
                rarity=api_card.get("rarity"),
                game="one_piece",
                image_url=image_url,
            )
            db.add(card)
            created += 1
        else:
            updated += 1

        if market_price is not None:
            card.current_price_usd = market_price
            card.current_price_updated_at = now
            db.flush()
            db.add(
                Price(
                    card_id=card.id,
                    source="one_piece_api",
                    price_usd=market_price,
                    condition="near_mint",
                )
            )

        db.commit()

    logger.info("Synced set %s: %d created, %d updated", set_id, created, updated)
    return created, updated


def sync_all_sets(db: Session) -> dict:
    """Sync every main set. Returns a summary of results and failures."""
    set_ids = list_set_ids()
    logger.info("Discovered %d One Piece sets", len(set_ids))

    total_created, total_updated = 0, 0
    failures: list[tuple[str, str]] = []


    for set_id in set_ids:
        try:
            created, updated = sync_set(db, set_id)
        except Exception as exc:
            logger.exception("Set %s failed, continuing with remaining sets", set_id)
            db.rollback()
            failures.append((set_id, str(exc)))
            continue

        total_created += created
        total_updated += updated

    return {
        "sets_attempted": len(set_ids),
        "sets_failed": len(failures),
        "created": total_created,
        "updated": total_updated,
        "failures": failures,
    }