"""allow scrydex as price source

Revision ID: 4f4fabc87c75
Revises: 7a4e076c1b36
Create Date: 2026-07-30 02:03:05.693538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f4fabc87c75'
down_revision: Union[str, Sequence[str], None] = '7a4e076c1b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('prices_source_check', 'prices', type_='check')
    op.create_check_constraint(
        'prices_source_check',
        'prices',
        "source IN ('tcgplayer', 'ebay', 'one_piece_api', 'scrydex')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('prices_source_check', 'prices', type_='check')
    op.create_check_constraint(
        'prices_source_check',
        'prices',
        "source IN ('tcgplayer', 'ebay', 'one_piece_api')",
    )