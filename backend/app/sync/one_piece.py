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

def list_deck_ids() -> list[str]:
    """Fetch every deck ID (OP/EB/PRB) from optcgapi."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.get("/allDecks/")
        response.raise_for_status()
        decks = response.json()

    return [d["structure_deck_id"] for d in decks]

def _upsert_card(
        db: Session,
        api_card: dict,
        external_id: str,
        now: datetime,
) -> bool:
    """Upsert one card and its price row, committing. Returns True if created."""
    market = api_card.get("market_price")
    market_price = Decimal(str(market)) if market is not None else None

    card = db.scalar(
        select(Card).where(Card.external_id == external_id)
    )
    created = card is None

    if created:
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
    return created

def sync_set(db: Session, set_id: str, endpoint: str = "sets") -> tuple[int, int]:
    """Sync all cards (and print variants) in one set. Returns (created, updated)."""
    created, updated = 0, 0
    now = datetime.now(timezone.utc)

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.get(f"/{endpoint}/{set_id}/")
        response.raise_for_status()
        api_cards = response.json()

    for api_card in api_cards:
        if _upsert_card(db, api_card, api_card["card_image_id"], now):
            created += 1
        else:
            updated += 1
    
    logger.info("Synced %s %s: %d created, %d updated", endpoint, set_id, created, updated)
    return created, updated

def sync_promos(db: Session) -> tuple[int, int]:
    """Sync all promo cards. Returns (created, updated)."""
    created, updated = 0, 0
    now = datetime.now(timezone.utc)

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.get("/allPromos/")
        response.raise_for_status()
        api_cards = response.json()

    for api_card in api_cards:
        image_url = api_card.get("card_image") or ""
        filename = image_url.rsplit("/", 1)[-1].removesuffix(".jpg")
        if not filename:
            logger.warning(
                "Promo card %r has no usable image filename, skipping",
                api_card.get("card_name"),
            )
            continue
        external_id = f"promo_{filename}"

        if _upsert_card(db, api_card, external_id, now):
            created += 1
        else:
            updated += 1

    logger.info("Synced promos: %d created, %d updated", created, updated)
    return created, updated


def sync_all_sets(db: Session) -> dict:
    """Sync every main set, structured deck and promo card. Returns a summary of results and failures."""
    
    targets = [(set_id, "sets") for set_id in list_set_ids()]
    targets += [(deck_id, "decks") for deck_id in list_deck_ids()]
    logger.info("Discovered %d One Piece sets/decks", len(targets))

    total_created, total_updated = 0, 0
    failures: list[tuple[str, str, str]] = []


    for set_id, endpoint in targets:
        try:
            created, updated = sync_set(db, set_id, endpoint=endpoint)
        except Exception as exc:
            logger.exception("%s %s failed, continuing", endpoint, set_id)
            db.rollback()
            failures.append((set_id, endpoint, str(exc)))
            continue

        total_created += created
        total_updated += updated

    try:
        created, updated = sync_promos(db)
        total_created += created
        total_updated += updated
    except Exception as exc:
        logger.exception("Promos sync failed")
        db.rollback()
        failures.append(("promos", "promos", str(exc)))
            

    if failures:
        logger.info("Retrying %d failed syncs", len(failures))
        remaining_failures: list[tuple[str, str, str]] = []

        for set_id, endpoint, _ in failures:
            try:
                if endpoint == "promos":
                    created, updated = sync_promos(db)
                else:
                    created, updated = sync_set(db, set_id, endpoint=endpoint)
            except Exception as exc:
                logger.exception("%s %s failed again on retry", endpoint, set_id)
                db.rollback()
                remaining_failures.append((set_id, endpoint, str(exc)))
                continue

            total_created += created
            total_updated += updated

        failures = remaining_failures
        

    return {
        "sets_attempted": len(targets) + 1,
        "sets_failed": len(failures),
        "created": total_created,
        "updated": total_updated,
        "failures": [(set_id, error) for set_id, _, error in failures],
    }