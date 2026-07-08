"""Seed the cards table with sample Pokemon and One Piece cards.

Run from the backend/ directory:
    python -m scripts.seed_cards

Safe to run multiple times: existing cards (by external_id) are skipped.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Card

SEED_CARDS = [
    # --- Pokemon ---
    {
        "external_id": "seed-pkm-001",
        "name": "Charizard ex",
        "set_name": "Scarlet & Violet 151",
        "card_number": "199/165",
        "rarity": "Special Illustration Rare",
        "game": "pokemon",
        "current_price_usd": Decimal("312.50"),
    },
    {
        "external_id": "seed-pkm-002",
        "name": "Pikachu",
        "set_name": "Scarlet & Violet 151",
        "card_number": "025/165",
        "rarity": "Common",
        "game": "pokemon",
        "current_price_usd": Decimal("0.25"),
    },
    {
        "external_id": "seed-pkm-003",
        "name": "Charmander",
        "set_name": "Scarlet & Violet 151",
        "card_number": "004/165",
        "rarity": "Common",
        "game": "pokemon",
        "current_price_usd": Decimal("0.30"),
    },
    {
        "external_id": "seed-pkm-004",
        "name": "Mew ex",
        "set_name": "Scarlet & Violet 151",
        "card_number": "205/165",
        "rarity": "Hyper Rare",
        "game": "pokemon",
        "current_price_usd": Decimal("44.99"),
    },
    {
        "external_id": "seed-pkm-005",
        "name": "Umbreon VMAX",
        "set_name": "Evolving Skies",
        "card_number": "215/203",
        "rarity": "Alternate Art Secret",
        "game": "pokemon",
        "current_price_usd": Decimal("1450.00"),
    },
    # --- One Piece ---
    {
        "external_id": "seed-op-001",
        "name": "Monkey.D.Luffy",
        "set_name": "Romance Dawn OP-01",
        "card_number": "OP01-003",
        "rarity": "Leader",
        "game": "one_piece",
        "current_price_usd": Decimal("4.50"),
    },
    {
        "external_id": "seed-op-002",
        "name": "Shanks",
        "set_name": "Romance Dawn OP-01",
        "card_number": "OP01-120",
        "rarity": "Secret Rare",
        "game": "one_piece",
        "current_price_usd": Decimal("135.00"),
    },
    {
        "external_id": "seed-op-003",
        "name": "Roronoa Zoro",
        "set_name": "Romance Dawn OP-01",
        "card_number": "OP01-025",
        "rarity": "Super Rare",
        "game": "one_piece",
        "current_price_usd": Decimal("12.75"),
    },
    {
        "external_id": "seed-op-004",
        "name": "Nami",
        "set_name": "Romance Dawn OP-01",
        "card_number": "OP01-016",
        "rarity": "Rare",
        "game": "one_piece",
        "current_price_usd": Decimal("2.10"),
    },
    {
        "external_id": "seed-op-005",
        "name": "Portgas.D.Ace",
        "set_name": "Paramount War OP-02",
        "card_number": "OP02-013",
        "rarity": "Super Rare",
        "game": "one_piece",
        "current_price_usd": Decimal("28.00"),
    },
]

def main() -> None:
    db = SessionLocal()
    created, skipped = 0, 0

    try:
        for card_data in SEED_CARDS:
            exists = db.scalar(
                select(Card).where(Card.external_id == card_data["external_id"])
            )
            if exists is not None:
                skipped += 1
                continue
                
            card = Card(
                **card_data,
                current_price_updated_at=datetime.now(timezone.utc),
            )
            db.add(card)
            created += 1

        db.commit()
        print(f"✓ Seed complete: {created}, created, {skipped} skipped")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()