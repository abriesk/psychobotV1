import os
from app.models import Settings
from sqlalchemy import select

async def get_settings(session):
    result = await session.execute(select(Settings).where(Settings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = Settings(id=1)
        session.add(settings)
        await session.commit()
    return settings

def get_landing_path(topic, lang):
    return f"/app/landings/{topic}_{lang}.html"