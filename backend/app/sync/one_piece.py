"""Sync One Piece cards and prices from the OPTCG API (optcgapi.com)."""


import logging 
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session


from app.models import Card, Price

logger = logging.getLogger(__name__)

BASE_URL = "https://optcgapi.com/api"


def sync_set(db: Session, set_id: str) -> tuple[int, int]:
    """Sync all cards (and print variants) in one set. Returns (created, updated)."""
    created, updated= 0, 0
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
            card = Card(
                external_id=external_id,
                name=api_card["card_name"],
                set_name=api_card.get("set_name"),
                card_number=api_card.get("card_set_id"),
                rarity=api_card.get("rarity"),
                game="one_piece",
                image_url=api_card.get("card_image"),
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
        