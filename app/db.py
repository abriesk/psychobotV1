# app/db.py - v1.1 with timezone auto-population
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
    
    # Auto-populate defaults (translations, settings, timezones)
    await _populate_defaults()


async def _populate_defaults():
    """
    Populate default data for fresh installations.
    Idempotent - safe to run multiple times.
    """
    from app.models import Translation, Settings, Timezone, DEFAULT_TIMEZONES
    from app.translations import TEXTS_DEFAULTS
    
    async with AsyncSessionLocal() as session:
        # ====================================================================
        # TRANSLATIONS
        # ====================================================================
        result = await session.execute(select(Translation).limit(1))
        if not result.scalar_one_or_none():
            print("📝 Translations table empty - populating from defaults...")
            
            count = 0
            for lang, texts in TEXTS_DEFAULTS.items():
                for key, value in texts.items():
                    translation = Translation(lang=lang, key=key, value=value)
                    session.add(translation)
                    count += 1
            
            await session.commit()
            print(f"✅ Populated {count} translations from TEXTS_DEFAULTS")
        
        # ====================================================================
        # SETTINGS
        # ====================================================================
        result = await session.execute(select(Settings).where(Settings.id == 1))
        if not result.scalar_one_or_none():
            print("⚙️  Creating default settings row...")
            settings = Settings(id=1)
            session.add(settings)
            await session.commit()
            print("✅ Default settings created")
        
        # ====================================================================
        # TIMEZONES (NEW v1.1)
        # ====================================================================
        result = await session.execute(select(Timezone).limit(1))
        if not result.scalar_one_or_none():
            print("🌍 Timezones table empty - populating defaults...")
            
            for tz_data in DEFAULT_TIMEZONES:
                timezone = Timezone(
                    offset_str=tz_data["offset_str"],
                    offset_minutes=tz_data["offset_minutes"],
                    display_name=tz_data["display_name"],
                    is_active=True,
                    sort_order=tz_data["sort_order"]
                )
                session.add(timezone)
            
            await session.commit()
            print(f"✅ Populated {len(DEFAULT_TIMEZONES)} default timezones")


# ============================================================================
# TIMEZONE HELPERS (for use in handlers)
# ============================================================================

async def get_active_timezones():
    """
    Get all active timezones, ordered by sort_order.
    Used by Telegram bot and web interface.
    """
    from app.models import Timezone
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Timezone)
            .where(Timezone.is_active == True)
            .order_by(Timezone.sort_order, Timezone.offset_minutes)
        )
        return result.scalars().all()


async def get_timezone_by_offset(offset_str: str):
    """
    Get timezone by offset string (e.g., "UTC+4").
    Returns None if not found.
    """
    from app.models import Timezone
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Timezone).where(Timezone.offset_str == offset_str)
        )
        return result.scalar_one_or_none()
