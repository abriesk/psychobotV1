"""
Data migration script: Populate Translations table from TEXTS_DEFAULTS
Run ONCE after schema migration.

Usage:
  docker-compose run --rm bot python -m migrations.migrate_translations_to_db
"""
import asyncio
import os
import sys
from sqlalchemy import select
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.db import AsyncSessionLocal
from app.models import Translation
from app.translations import TEXTS_DEFAULTS


async def migrate_translations():
    """
    Migrate all translations from TEXTS_DEFAULTS dict to database.
    Idempotent - safe to run multiple times.
    """
    print("🔄 Starting translation migration...")
    
    async with AsyncSessionLocal() as session:
        # Check if already populated
        result = await session.execute(select(Translation).limit(1))
        if result.scalar_one_or_none():
            print("⚠️  Translations table already has data.")
            response = input("Do you want to REPLACE all translations? [y/N]: ")
            
            if response.lower() != 'y':
                print("❌ Migration cancelled.")
                return
            
            # Clear existing translations
            print("🗑️  Clearing existing translations...")
            await session.execute(Translation.__table__.delete())
            await session.commit()
        
        # Populate from TEXTS_DEFAULTS dictionary
        total = 0
        for lang, texts in TEXTS_DEFAULTS.items():
            for key, value in texts.items():
                translation = Translation(lang=lang, key=key, value=value)
                session.add(translation)
                total += 1
        
        await session.commit()
        print(f"✅ Successfully migrated {total} translations to database")
        
        # Verification
        result = await session.execute(select(Translation))
        count = len(result.scalars().all())
        print(f"✅ Verified: {count} translations in database")
        
        # Show breakdown by language
        for lang in TEXTS_DEFAULTS.keys():
            result = await session.execute(
                select(Translation).where(Translation.lang == lang)
            )
            lang_count = len(result.scalars().all())
            print(f"   - {lang}: {lang_count} translations")


if __name__ == '__main__':
    asyncio.run(migrate_translations())
