"""v1.0 schema: translations, slots, extended settings and requests (FIXED)

Revision ID: 001_v1_0_schema
Revises: 
Create Date: 2025-12-25 09:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_v1_0_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade to v1.0 schema.
    Creates new tables and extends existing ones.
    """
    
    # ========================================================================
    # NEW TABLE: translations
    # ========================================================================
    op.create_table(
        'translations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lang', sa.String(length=2), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lang', 'key', name='uix_lang_key')
    )
    op.create_index('ix_translations_lang', 'translations', ['lang'])
    op.create_index('ix_translations_key', 'translations', ['key'])
    
    # ========================================================================
    # NEW TABLE: slots (FIXED - no request_id FK, simpler design)
    # ========================================================================
    op.create_table(
        'slots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('is_online', sa.Boolean(), nullable=True),
        sa.Column('status', sa.Enum('AVAILABLE', 'BOOKED', 'HELD', name='slotstatus'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_slots_start_time', 'slots', ['start_time'])
    op.create_index('ix_slots_status', 'slots', ['status'])
    
    # ========================================================================
    # EXTEND: settings table
    # ========================================================================
    op.add_column('settings', sa.Column('auto_confirm_slots', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('settings', sa.Column('reminder_24h_enabled', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('settings', sa.Column('reminder_1h_enabled', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('settings', sa.Column('cancel_window_hours', sa.Integer(), nullable=True, server_default='24'))
    
    # ========================================================================
    # EXTEND: requests table
    # ========================================================================
    
    # Add CANCELED to existing RequestStatus enum
    op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'CANCELED'")
    
    op.add_column('requests', sa.Column('slot_id', sa.Integer(), nullable=True))
    op.add_column('requests', sa.Column('scheduled_datetime', sa.DateTime(), nullable=True))
    op.add_column('requests', sa.Column('reminder_24h_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('requests', sa.Column('reminder_1h_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('requests', sa.Column('reminders_log', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('requests', sa.Column('cancelled_at', sa.DateTime(), nullable=True))
    
    # Create FK from Request to Slot (one-way relationship)
    op.create_foreign_key('fk_requests_slot_id', 'requests', 'slots', ['slot_id'], ['id'])


def downgrade() -> None:
    """Downgrade from v1.0 to v0.8."""
    
    # Remove requests extensions
    op.drop_constraint('fk_requests_slot_id', 'requests', type_='foreignkey')
    op.drop_column('requests', 'cancelled_at')
    op.drop_column('requests', 'reminders_log')
    op.drop_column('requests', 'reminder_1h_sent')
    op.drop_column('requests', 'reminder_24h_sent')
    op.drop_column('requests', 'scheduled_datetime')
    op.drop_column('requests', 'slot_id')
    
    # Remove settings extensions
    op.drop_column('settings', 'cancel_window_hours')
    op.drop_column('settings', 'reminder_1h_enabled')
    op.drop_column('settings', 'reminder_24h_enabled')
    op.drop_column('settings', 'auto_confirm_slots')
    
    # Drop slots table
    op.drop_index('ix_slots_status', table_name='slots')
    op.drop_index('ix_slots_start_time', table_name='slots')
    op.drop_table('slots')
    
    # Drop translations table
    op.drop_index('ix_translations_key', table_name='translations')
    op.drop_index('ix_translations_lang', table_name='translations')
    op.drop_table('translations')
