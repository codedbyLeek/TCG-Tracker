"""One-off script to verify database connectivity and model operations.

Run from the backend/ directory:
    python -m scripts.test_db
"""

import uuid
from decimal import Decimal

from app.core.database import SessionLocal
from app.models import User, Card, CollectionItem


def main() -> None:
    db = SessionLocal()

    try:
        #1. CREATE a test user
        test_user = User(
            clerk_user_id=f"test_clerk_{uuid.uuid4().hex[:8]}",
            email="test@example.com",
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        print(f"✓ Created user: {test_user.id} ({test_user.email})")

        #2. CREATE a test card
        test_card = Card(
            external_id=f"test_ext_{uuid.uuid4().hex[:8]}",
            name="Charizard ex",
            set_name="Scarlet & Violet 151",
            card_number="199/165",
            rarity="Special Illustration Rare",
            game="pokemon",
            current_price_usd=Decimal("45.00"),
        )
        db.add(test_card)
        db.commit()
        db.refresh(test_card)
        print(f"✓ Created card: {test_card.id} ({test_card.name})")


        #3. ADD the card to the user's collection
        item = CollectionItem(
            user_id=test_user.id,
            card_id=test_card.id,
            quantity=2,
            condition="near_mint",
        )
        db.add(item)
        db.commit()
        print(f"✓ Added {item.quantity}x {test_card.name} to collection")


        # 4. QUERY it back through the relationship
        fetched_user = db.get(User, test_user.id)
        print(f"✓ User {fetched_user.email} owns:")
        total = Decimal("0")
        for ci in fetched_user.collection_items:
            line_value = ci.card.current_price_usd * ci.quantity
            total += line_value
            print(f"    {ci.quantity}x {ci.card.name} @ ${ci.card.current_price_usd} = ${line_value}")
        print(f"✓ Collection total: ${total}")

        # 5. CLEAN UP test data
        db.delete(item)
        db.delete(test_card)
        db.delete(test_user)
        db.commit()
        print("✓ Test data cleaned up")

        print("\n🎉 ALL DATABASE OPERATIONS SUCCESSFUL")

    except Exception as e:
        db.rollback()
        print(f"✗ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()