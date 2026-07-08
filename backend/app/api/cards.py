import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session


from app.core.database import get_db
from app.models import Card
from app.schemas.card import CardListResponse, CardResponse

router = APIRouter(prefix="/api/cards", tags=["cards"])



@router.get("", response_model=CardListResponse)
def search_cards(
    q: str | None = Query(default=None, description="Search by card name"),
    game: str | None =Query(default=None, description="Filter: pokemon or one_piece"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Search the catalog."""
    stmt = select(Card)

    if q:
        stmt = stmt.where(Card.name.ilike(f"%{q}%"))
    if game:
        stmt = stmt.where(Card.game == game)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    cards = db.scalars(stmt.order_by(Card.name).limit(limit).offset(offset)).all()

    return CardListResponse(items=cards, total=total, limit=limit, offset=offset)


@router.get("/{card_id}", response_model=CardResponse)
def get_card(card_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a single card by ID."""
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card