"""add fund_favorites table

Revision ID: a1b2c3d4e5f6
Revises: 5ca8e7d44e60
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5ca8e7d44e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('fund_favorites',
    sa.Column('fund_id', sa.Integer(), nullable=False),
    sa.Column('favorited_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['fund_id'], ['funds.id'], ),
    sa.PrimaryKeyConstraint('fund_id')
    )


def downgrade() -> None:
    op.drop_table('fund_favorites')
