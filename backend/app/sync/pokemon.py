import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Card, Price
from app.core.storage import upload_image_to_r2

logger = logging.getLogger(__name__)

BASE_URL = "https://api.scrydex.com/pokemon/v1"
PAGE_SIZE = 100  # Scrydex max is 100 (pokemontcg.io allowed 250)

CONDITION_PRIORITY = ("NM", "LP", "MP", "HP", "DM")


def _build_headers() -> dict:
    """Scrydex requires both headers on every request - no unauthenticated tier."""
    return {
        "X-Api-Key": settings.SCRYDEX_API_KEY,
        "X-Team-ID": settings.SCRYDEX_TEAM_ID,
    }


def _extract_market_price(api_card: dict) -> Decimal | None:
    """Pull the best available raw USD market price from the card's variants."""
    best_by_condition: dict[str, Decimal] = {}

    for variant in api_card.get("variants", []):
        for price in variant.get("prices", []):
            if price.get("type") != "raw":
                continue
            if price.get("currency") != "USD":
                continue
            market = price.get("market")
            condition = price.get("condition")
            if market is None or condition is None:
                continue
            if condition not in best_by_condition:
                best_by_condition[condition] = Decimal(str(market))

    for condition in CONDITION_PRIORITY:
        if condition in best_by_condition:
            return best_by_condition[condition]
    return None


def _extract_image_url(api_card: dict) -> str | None:
    """Find the front-facing large image URL, if present."""
    for image in api_card.get("images", []):
        if image.get("type") == "front":
            return image.get("large")
    return None


def sync_set(db: Session, set_id: str) -> tuple[int, int]:
    """Sync all cards in one expansion from Scrydex into the database."""
    created, updated = 0, 0
    page = 1
    now = datetime.now(timezone.utc)

    with httpx.Client(base_url=BASE_URL, headers=_build_headers(), timeout=30.0) as client:
        while True:
            response = client.get(
                f"/expansions/{set_id}/cards",
                params={
                    "include": "prices",
                    "page": page,
                    "pageSize": PAGE_SIZE,
                },
            )
            response.raise_for_status()
            payload = response.json()
            api_cards = payload.get("data", [])

            if not api_cards:
                break

            for api_card in api_cards:
                market_price = _extract_market_price(api_card)

                card = db.scalar(
                    select(Card).where(Card.external_id == api_card["id"])
                )

                if card is None:
                    source_image_url = _extract_image_url(api_card)
                    image_url = source_image_url

                    if source_image_url is not None:
                        try:
                            image_url = upload_image_to_r2(
                                source_url=source_image_url,
                                game="pokemon",
                                external_id=api_card["id"],
                            )
                        except Exception:
                            logger.warning(
                                "Failed to upload image to R2 for card %s, using source URL instead",
                                api_card["id"],
                                exc_info=True,
                            )

                    card = Card(
                        external_id=api_card["id"],
                        name=api_card["name"],
                        set_name=api_card.get("expansion", {}).get("name"),
                        card_number=api_card.get("number"),
                        rarity=api_card.get("rarity"),
                        game="pokemon",
                        image_url=_extract_image_url(api_card),
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
                            source="scrydex",
                            price_usd=market_price,
                            condition="near_mint",
                        )
                    )

                db.commit()
                
            total_count = payload.get("totalCount") or payload.get("total_count") or 0
            total_fetched = (page - 1) * PAGE_SIZE + len(api_cards)
            if total_fetched >= total_count:
                break

            page += 1


    logger.info("Synced set %s: %d created, %d updated", set_id, created, updated)
    return created, updated