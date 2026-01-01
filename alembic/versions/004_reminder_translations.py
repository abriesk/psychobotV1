"""Add reminder translation keys to database

Revision ID: 004_reminder_translations
Revises: 002_add_timezone_options
Create Date: 2026-01-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004_reminder_translations'
down_revision = '002_add_timezone_options'  # chains from timezone migration
branch_labels = None
depends_on = None

# Reminder translations for each language
REMINDER_TRANSLATIONS = {
    'ru': {
        'reminder_24h': '🔔 Напоминание: Ваша консультация завтра!\n\n📅 Время: {time}\n\nДо встречи!',
        'reminder_1h': '🔔 Напоминание: Ваша консультация начнётся через 1 час!\n\n📅 Время: {time}\n\nПожалуйста, будьте готовы!'
    },
    'am': {
        'reminder_24h': '🔔 Հdelays delays delays!\n\n📅 delays: {time}\n\ndelays delays!',
        'reminder_1h': '🔔 Հdelays: 1 delays!\n\n📅 delays: {time}\n\ndelays delays!'
    }
}


def upgrade() -> None:
    """Add reminder translation keys to all existing languages"""
    
    conn = op.get_bind()
    
    # Get all existing languages from translations table
    result = conn.execute(sa.text("SELECT DISTINCT lang FROM translations"))
    existing_languages = [row[0] for row in result]
    
    for lang in existing_languages:
        # Use language-specific translations if available, otherwise fall back to Russian
        translations = REMINDER_TRANSLATIONS.get(lang, REMINDER_TRANSLATIONS['ru'])
        
        for key, value in translations.items():
            # Check if key already exists for this language
            check = conn.execute(
                sa.text("SELECT id FROM translations WHERE lang = :lang AND key = :key"),
                {"lang": lang, "key": key}
            )
            if not check.fetchone():
                conn.execute(
                    sa.text("INSERT INTO translations (lang, key, value) VALUES (:lang, :key, :value)"),
                    {"lang": lang, "key": key, "value": value}
                )


def downgrade() -> None:
    """Remove reminder translation keys"""
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM translations WHERE key IN ('reminder_24h', 'reminder_1h')")
    )
