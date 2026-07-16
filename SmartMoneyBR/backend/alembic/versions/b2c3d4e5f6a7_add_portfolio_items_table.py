"""add portfolio_items table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('portfolio_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_username', sa.String(length=80), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('added_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_username', 'asset_id', name='uq_portfolio_owner_asset')
    )
    op.create_index(op.f('ix_portfolio_items_owner_username'), 'portfolio_items', ['owner_username'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_portfolio_items_owner_username'), table_name='portfolio_items')
    op.drop_table('portfolio_items')
