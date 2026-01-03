"""v1.1 add timezones table

Revision ID: 002_v1_1_timezones
Revises: 001_v1_0_schema
Create Date: 2025-12-31 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '002_v1_1_timezones'
down_revision = '001_v1_0_schema'
branch_labels = None
depends_on = None

# Default timezone data to seed
DEFAULT_TIMEZONES = [
    {"offset_str": "UTC+4", "offset_minutes": 240, "display_name": "Yerevan, Dubai, Baku", "sort_order": 1},
    {"offset_str": "UTC+3", "offset_minutes": 180, "display_name": "Moscow, Istanbul, Minsk", "sort_order": 2},
    {"offset_str": "UTC+2", "offset_minutes": 120, "display_name": "Kyiv, Athens, Helsinki", "sort_order": 3},
    {"offset_str": "UTC+1", "offset_minutes": 60, "display_name": "Berlin, Paris, Rome", "sort_order": 4},
    {"offset_str": "UTC+0", "offset_minutes": 0, "display_name": "London, Lisbon, Dublin", "sort_order": 5},
    {"offset_str": "UTC-5", "offset_minutes": -300, "display_name": "New York, Toronto, Miami", "sort_order": 6},
    {"offset_str": "UTC-8", "offset_minutes": -480, "display_name": "Los Angeles, Vancouver", "sort_order": 7},
]


def upgrade() -> None:
    """
    Create timezones table and seed with default data.
    """
    # Create timezones table
    timezones_table = op.create_table(
        'timezones',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('offset_str', sa.String(length=10), nullable=False),
        sa.Column('offset_minutes', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('offset_str', name='uix_timezone_offset_str')
    )
    
    # Create index for active timezones
    op.create_index('ix_timezones_is_active', 'timezones', ['is_active'])
    
    # Seed default timezone data
    now = datetime.utcnow()
    op.bulk_insert(
        timezones_table,
        [
            {
                "offset_str": tz["offset_str"],
                "offset_minutes": tz["offset_minutes"],
                "display_name": tz["display_name"],
                "is_active": True,
                "sort_order": tz["sort_order"],
                "created_at": now,
                "updated_at": now
            }
            for tz in DEFAULT_TIMEZONES
        ]
    )


def downgrade() -> None:
    """
    Drop timezones table.
    """
    op.drop_index('ix_timezones_is_active', table_name='timezones')
    op.drop_table('timezones')
