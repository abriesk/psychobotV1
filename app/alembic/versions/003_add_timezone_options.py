"""v1.0.1: Add timezone_options to settings

Revision ID: 002_add_timezone_options
Revises: 001_v1_0_schema
Create Date: 2025-12-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_add_timezone_options'
down_revision = '002_notification_queue'
branch_labels = None
depends_on = None

# Default timezone options (matching models.py)
DEFAULT_TIMEZONE_OPTIONS = [
    {"code": "UTC+4", "label": {"ru": "Ереван", "am": "Yerevan"}, "emoji": "🇦🇲", "order": 1},
    {"code": "UTC+3", "label": {"ru": "Москва", "am": "Moscow"}, "emoji": "🇷🇺", "order": 2},
    {"code": "UTC+2", "label": {"ru": "Киев", "am": "Kyiv"}, "emoji": "🇺🇦", "order": 3},
    {"code": "UTC+1", "label": {"ru": "Берлин", "am": "Berlin"}, "emoji": "🇩🇪", "order": 4},
    {"code": "UTC+0", "label": {"ru": "Лондон", "am": "London"}, "emoji": "🇬🇧", "order": 5},
    {"code": "UTC-5", "label": {"ru": "Нью-Йорк", "am": "New York"}, "emoji": "🇺🇸", "order": 6},
]


def upgrade() -> None:
    """Add timezone_options column to settings table"""
    
    # Add column as nullable first
    op.add_column('settings', 
        sa.Column('timezone_options', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )
    
    # Set default value for existing rows
    import json
    op.execute(
        f"UPDATE settings SET timezone_options = '{json.dumps(DEFAULT_TIMEZONE_OPTIONS)}' WHERE timezone_options IS NULL"
    )


def downgrade() -> None:
    """Remove timezone_options column"""
    op.drop_column('settings', 'timezone_options')
