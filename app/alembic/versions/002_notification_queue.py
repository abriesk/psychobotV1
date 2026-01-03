"""Add pending_notifications table for Web-to-Bot communication

Revision ID: 002_notification_queue
Revises: 001_v1_0_schema
Create Date: 2025-12-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_notification_queue'
down_revision = '001_v1_0_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pending_notifications table"""
    
    # Create notification type enum
    op.execute("CREATE TYPE notificationtype AS ENUM ('proposal', 'confirmation', 'rejection', 'reminder', 'custom')")
    
    # Create pending_notifications table
    op.create_table(
        'pending_notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=True),
        sa.Column('notification_type', sa.Enum('proposal', 'confirmation', 'rejection', 'reminder', 'custom', name='notificationtype'), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('proposed_time', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=True, server_default='0'),
        sa.ForeignKeyConstraint(['request_id'], ['requests.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pending_notifications_user_id', 'pending_notifications', ['user_id'])
    op.create_index('ix_pending_notifications_sent_at', 'pending_notifications', ['sent_at'])


def downgrade() -> None:
    """Remove pending_notifications table"""
    op.drop_index('ix_pending_notifications_sent_at', table_name='pending_notifications')
    op.drop_index('ix_pending_notifications_user_id', table_name='pending_notifications')
    op.drop_table('pending_notifications')
    op.execute("DROP TYPE notificationtype")
