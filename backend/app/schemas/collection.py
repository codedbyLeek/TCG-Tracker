import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.card import CardResponse


class CollectionItemCreate(BaseModel):
    """Shape of the requst body when adding a card to the collection"""


    card_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=9999)
    condition: str | None= None


class CollectionItemResponse(BaseModel):
    """One item in the user's collection, with its card embedded."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quantity: int
    condition: str | None
    added_at: datetime
    card: CardResponse


class CollectionResponse(BaseModel):
    """The full collection view."""

    items: list[CollectionItemResponse]
    total_cards: int
    total_value_usd: Decimal