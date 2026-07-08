import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

class CardResponse(BaseModel):
    """SHape of a card return by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    set_name: str | None
    card_number: str | None
    rarity: str | None
    game: str
    image_url: str | None
    current_price_usd: Decimal | None
    current_price_updated_at: datetime | None


class CardListResponse(BaseModel):
    """Shape of a paginated card search result."""

    items: list[CardResponse]
    total: int
    limit: int
    offset: int