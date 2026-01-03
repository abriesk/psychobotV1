"""v0.8 base schema: users, settings, requests, negotiations

Revision ID: 000_base_schema
Revises: 
Create Date: 2025-12-20

This migration creates the original v0.8 base tables that
subsequent migrations depend on.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '000_base_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create v0.8 base schema tables."""
    
    # ========================================================================
    # ENUMS
    # ========================================================================
    op.execute("CREATE TYPE requesttype AS ENUM ('waitlist', 'individual', 'couple')")
    op.execute("CREATE TYPE requeststatus AS ENUM ('pending', 'negotiating', 'confirmed', 'rejected', 'canceled')")
    op.execute("CREATE TYPE sendertype AS ENUM ('admin', 'client')")
    
    # ========================================================================
    # TABLE: users
    # ========================================================================
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('language', sa.String(length=2), nullable=True, server_default='ru'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # ========================================================================
    # TABLE: settings
    # ========================================================================
    op.create_table(
        'settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('availability_on', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('individual_price', sa.String(), nullable=True, server_default="'50 USD / 60 min'"),
        sa.Column('couple_price', sa.String(), nullable=True, server_default="'70 USD / 60 min'"),
        sa.PrimaryKeyConstraint('id')
    )
    
    # ========================================================================
    # TABLE: requests
    # ========================================================================
    op.create_table(
        'requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_uuid', sa.String(), nullable=True, unique=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('type', sa.Enum('waitlist', 'individual', 'couple', name='requesttype'), nullable=True),
        sa.Column('onsite', sa.Boolean(), nullable=True),
        sa.Column('timezone', sa.String(), nullable=True),
        sa.Column('desired_time', sa.String(), nullable=True),
        sa.Column('problem', sa.Text(), nullable=True),
        sa.Column('address_name', sa.String(), nullable=True),
        sa.Column('preferred_comm', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'negotiating', 'confirmed', 'rejected', 'canceled', name='requeststatus'), 
                  nullable=True, server_default='pending'),
        sa.Column('final_time', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # ========================================================================
    # TABLE: negotiations
    # ========================================================================
    op.create_table(
        'negotiations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('requests.id'), nullable=True),
        sa.Column('sender', sa.Enum('admin', 'client', name='sendertype'), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


    # ========================================================================
    # TABLE: timezones (v1.1 - but needed for fresh install)
    # ========================================================================
    op.create_table(
        'timezones',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('offset_str', sa.String(length=10), nullable=False, unique=True),
        sa.Column('offset_minutes', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_timezones_is_active', 'timezones', ['is_active'])


def downgrade() -> None:
    """Drop v0.8 base schema tables."""
    op.drop_index('ix_timezones_is_active', table_name='timezones')
    op.drop_table('timezones')
    op.drop_table('negotiations')
    op.drop_table('requests')
    op.drop_table('settings')
    op.drop_table('users')
    
    op.execute("DROP TYPE sendertype")
    op.execute("DROP TYPE requeststatus")
    op.execute("DROP TYPE requesttype")
