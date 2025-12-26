# app/db.py - v1.0 with auto-population on fresh install
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import select

DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    """
    Initialize database schema and populate with defaults.
    Safe for both fresh installs and existing databases.
    """
    # Create all tables from models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ Database schema initialized.")
    
    # Auto-populate translations if table is empty (fresh install)
    await _populate_defaults()


async def _populate_defaults():
    """
    Populate default data for fresh installations.
    Idempotent - safe to run multiple times.
    """
    from app.models import Translation, Settings
    from app.translations import TEXTS_DEFAULTS
    
    async with AsyncSessionLocal() as session:
        # Check if translations exist
        result = await session.execute(select(Translation).limit(1))
        if not result.scalar_one_or_none():
            print("📝 Translations table empty - populating from defaults...")
            
            # Populate from TEXTS_DEFAULTS
            count = 0
            for lang, texts in TEXTS_DEFAULTS.items():
                for key, value in texts.items():
                    translation = Translation(lang=lang, key=key, value=value)
                    session.add(translation)
                    count += 1
            
            await session.commit()
            print(f"✅ Populated {count} translations from TEXTS_DEFAULTS")
        
        # Ensure Settings row exists
        result = await session.execute(select(Settings).where(Settings.id == 1))
        if not result.scalar_one_or_none():
            print("⚙️  Creating default settings row...")
            settings = Settings(id=1)
            session.add(settings)
            await session.commit()
            print("✅ Default settings created")
