"""Sync Pokemon cards and prices from the Pokemon TCG API (pokemontcg.io)."""

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Card, Price

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pokemontcg.io/v2"
PAGE_SIZE = 250


def _build_headers() -> dict:
    """API key is optional but grants higher rate limits."""
    if settings.POKEMON_TCG_API_KEY:
        return {"X-Api-Key": settings.POKEMON_TCG_API_KEY}
    logger.warning("POKEMON_TCG_API_KEY not set - using low unauthenticated rate limits")
    return {}


def _extract_market_price(api_card: dict) -> Decimal | None:
    """Pull the best available market price from tcgplayer data, if present."""
    prices = api_card.get("tcgplayer", {}).get("prices", {})
    for variant in ("holofoil", "reverseHolofoil", "normal", "1stEditionHolofoil"):
        market = prices.get(variant, {}).get("market")
        if market is not None:
            return Decimal(str(market))
    return None


def sync_set(db: Session, set_id: str) -> tuple[int, int]:
    """Sync all cards in one Pokemon set. Returns (created, updated)."""
    created, updated = 0, 0
    page = 1
    now = datetime.now(timezone.utc)

    with httpx.Client(base_url=BASE_URL, headers=_build_headers(), timeout=30.0) as client:
        while True:
            response = client.get(
                "/cards",
                params={
                    "q": f"set.id:{set_id}",
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
                    card = Card(
                        external_id=api_card["id"],
                        name=api_card["name"],
                        set_name=api_card.get("set", {}).get("name"),
                        card_number=api_card.get("number"),
                        rarity=api_card.get("rarity"),
                        game="pokemon",
                        image_url=api_card.get("images", {}).get("large"),
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
                            source="tcgplayer",
                            price_usd=market_price,
                            condition="near_mint",
                        )
                    )

            page += 1

    db.commit()
    logger.info("Synced set %s: %d created, %d updated", set_id, created, updated)
    return created, updated