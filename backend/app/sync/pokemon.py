import logging
from datetime import datetime, timedelta, timezone
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


def list_expansions() -> list[dict]:
    """Fetch all English physical-card expansions from Scrydex."""
    expansions: list[dict] = []
    page = 1

    with httpx.Client(base_url=BASE_URL, headers=_build_headers(), timeout=30.0) as client:
        while True:
            response = client.get(
                "/en/expansions",
                params={"page": page, "pageSize": PAGE_SIZE},
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", [])
            expansions.extend(data)


            total_count = payload.get("total_count") or 0
            if not data or len(expansions) >= total_count:
                break
            page += 1

    return [e for e in expansions if not e.get("is_online_only")]



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


def _sync_expansions(db: Session, expansions: list[dict]) -> dict:
    """Shared orchestration: sync the given expansions, isolating pre-expansion failures."""
    total_created, total_updated = 0, 0
    failures: list[tuple[str, str]] = []

    for expansion in expansions:
        expansion_id = expansion["id"]
        try:
            created, updated = sync_set(db, expansion_id)
        except Exception as exc:
            logger.exception(
                "Expansion %s failed, continuing with remaining expansions", expansion_id
            )
            db.rollback()
            failures.append((expansion_id, str(exc)))
            continue

        total_created += created
        total_updated += updated

    if failures:
        logger.info("Retrying %d failed expansions", len(failures))
        remaining_failures: list[tuple[str, str]] = []

        for expansion_id, _ in failures:
            try:
                created, updated = sync_set(db, expansion_id)
            except Exception as exc:
                logger.exception("Expansion %s failed again on retry", expansion_id)
                db.rollback()
                remaining_failures.append((expansion_id, str(exc)))
                continue

            total_created += created
            total_updated += updated

        failures = remaining_failures

    return {
        "sets_attempted": len(expansions),
        "sets_failed": len(failures),
        "created": total_created,
        "updated": total_updated,
        "failures": failures,
    }


def sync_all_expansions(db: Session) -> dict:
    """Sync every English physical expansion."""
    expansions = list_expansions()
    estimated_requests = sum(
        (e.get("total", 0) + PAGE_SIZE - 1) // PAGE_SIZE for e in expansions
    )
    logger.info(
        "Discovered %d Pokemon expansion (~%d card-page requests)",
        len(expansions),
        estimated_requests,
    )
    return _sync_expansions(db, expansions)


def sync_recent_expansions(db: Session, days: int = 90) -> dict:
    """Sync only expansions released within the last 'days' days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent: list[dict] = []

    for expansion in list_expansions():
        release_date = expansion.get("release_date")
        if not release_date:
            continue
        try:
            released_at = datetime.strptime(release_date, "%Y/%m/%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            logger.warning(
                "Expansion %s has unparseable release_date %r, skipping",
                expansion.get("id"),
                release_date,
            )
            continue
        if released_at >= cutoff:
            recent.append(expansion)


    logger.info(
        "%d expansion released in the last %d days", len(recent), days
    )
    return _sync_expansions(db, recent)