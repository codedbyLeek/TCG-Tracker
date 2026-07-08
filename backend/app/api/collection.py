import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models import Card, CollectionItem, User

from app.schemas.collection import (
    CollectionItemCreate,
    CollectionItemResponse,
    CollectionResponse,
)


router = APIRouter(prefix="/api/collection", tags=["collection"])

TEMP_CLERK_ID = "dev_temp_user"


def get_current_user(db: Session = Depends(get_db)) -> User:
    """TEMPORARY: fetch-or-create a dev user. Replaced by Clerk auth later."""
    user = db.scalar(select(User).where(User.clerk_user_id == TEMP_CLERK_ID))
    if user is None:
        user = User(clerk_user_id=TEMP_CLERK_ID, email="dev@tcgtracker.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user 


@router.get("", response_model=CollectionResponse)
def get_collection(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    """List the user's collection eith total value."""
    items = db.scalars(
        select(CollectionItem)
        .where(CollectionItem.user_id == user.id)
        .options(selectinload(CollectionItem.card))
        .order_by(CollectionItem.added_at.desc())
    ).all()

    total_cards = sum(item.quantity for item in items)
    total_value = sum(
        (item.card.current_price_usd or Decimal("0")) * item.quantity
        for item in items
    )

    return CollectionResponse(
        items=items,
        total_cards=total_cards,
        total_value_usd=total_value,
    )


@router.post("/items", response_model=CollectionItemResponse, status_code=201)
def add_to_collection(
    payload: CollectionItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a card to the collection, or bump quantity if already owned."""
    card = db.get(Card, payload.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    
    existing = db.scalar(
        select(CollectionItem).where(
            CollectionItem.user_id == user.id,
            CollectionItem.card_id == payload.card_id,
        )
    )

    if existing is not None:
        existing.quantity += payload.quantity
        db.commit()
        db.refresh(existing)
        return existing
    
    item = CollectionItem(
        user_id=user.id,
        card_id=payload.card_id,
        quantity=payload.quantity,
        condition=payload.condition,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=204)
def remove_from_collection(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove an item from the collection entirely."""
    item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.id == item_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Collection item not found")
    
    db.delete(item)
    db.commit()
    