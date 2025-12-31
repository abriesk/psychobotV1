# app/web/routers/admin.py - Admin management routes (v1.1 with Timezones)
"""
Admin routes for slot management, request handling, settings, landings, languages, and timezones.
Protected by Nginx Proxy Manager Basic Auth - no internal auth needed.
"""
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import Optional

from app.models import (
    Slot, SlotStatus, Request as BookingRequest, RequestStatus,
    Settings, Translation, Negotiation, SenderType, Timezone
)
from app.utils_slots import (
    parse_utc_offset, user_tz_to_utc, validate_slot_time,
    check_slot_overlap, format_slot_time
)
from app.web.dependencies import get_db
import os

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


# ============================================================================
# DASHBOARD
# ============================================================================

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Admin dashboard with statistics"""
    # Get statistics
    total_requests = await session.execute(select(func.count(BookingRequest.id)))
    total_requests = total_requests.scalar()
    
    pending_requests = await session.execute(
        select(func.count(BookingRequest.id)).where(BookingRequest.status == RequestStatus.PENDING)
    )
    pending_requests = pending_requests.scalar()
    
    upcoming_slots = await session.execute(
        select(func.count(Slot.id)).where(
            Slot.start_time > datetime.utcnow(),
            Slot.status == SlotStatus.AVAILABLE
        )
    )
    upcoming_slots = upcoming_slots.scalar()
    
    booked_slots = await session.execute(
        select(func.count(Slot.id)).where(Slot.status == SlotStatus.BOOKED)
    )
    booked_slots = booked_slots.scalar()
    
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "stats": {
                "total_requests": total_requests,
                "pending_requests": pending_requests,
                "upcoming_slots": upcoming_slots,
                "booked_slots": booked_slots
            }
        }
    )


# ============================================================================
# TIMEZONE MANAGEMENT (NEW v1.1)
# ============================================================================

@router.get("/timezones", response_class=HTMLResponse)
async def admin_timezones_page(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Timezone management page"""
    result = await session.execute(
        select(Timezone).order_by(Timezone.sort_order, Timezone.offset_minutes)
    )
    timezones = result.scalars().all()
    
    return templates.TemplateResponse(
        "admin/timezones.html",
        {
            "request": request,
            "timezones": timezones
        }
    )


@router.post("/timezones/add")
async def add_timezone(
    offset_str: str = Form(...),
    offset_minutes: int = Form(...),
    display_name: str = Form(...),
    sort_order: int = Form(10),
    session: AsyncSession = Depends(get_db)
):
    """Add a new timezone"""
    # Check if offset_str already exists
    result = await session.execute(
        select(Timezone).where(Timezone.offset_str == offset_str)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, f"Timezone {offset_str} already exists")
    
    # Validate offset format
    if not offset_str.startswith('UTC'):
        raise HTTPException(400, "Offset must start with 'UTC'")
    
    # Create timezone
    timezone = Timezone(
        offset_str=offset_str,
        offset_minutes=offset_minutes,
        display_name=display_name,
        is_active=True,
        sort_order=sort_order
    )
    session.add(timezone)
    await session.commit()
    
    return {"success": True, "id": timezone.id}


@router.post("/timezones/{tz_id}/update")
async def update_timezone(
    tz_id: int,
    display_name: Optional[str] = Form(None),
    sort_order: Optional[int] = Form(None),
    session: AsyncSession = Depends(get_db)
):
    """Update timezone display name or sort order"""
    result = await session.execute(select(Timezone).where(Timezone.id == tz_id))
    timezone = result.scalar_one_or_none()
    
    if not timezone:
        raise HTTPException(404, "Timezone not found")
    
    if display_name is not None:
        timezone.display_name = display_name
    if sort_order is not None:
        timezone.sort_order = sort_order
    
    await session.commit()
    return {"success": True}


@router.post("/timezones/{tz_id}/enable")
async def enable_timezone(
    tz_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Enable a timezone"""
    result = await session.execute(select(Timezone).where(Timezone.id == tz_id))
    timezone = result.scalar_one_or_none()
    
    if not timezone:
        raise HTTPException(404, "Timezone not found")
    
    timezone.is_active = True
    await session.commit()
    return {"success": True}


@router.post("/timezones/{tz_id}/disable")
async def disable_timezone(
    tz_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Disable a timezone"""
    result = await session.execute(select(Timezone).where(Timezone.id == tz_id))
    timezone = result.scalar_one_or_none()
    
    if not timezone:
        raise HTTPException(404, "Timezone not found")
    
    timezone.is_active = False
    await session.commit()
    return {"success": True}


@router.post("/timezones/{tz_id}/delete")
async def delete_timezone(
    tz_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Delete a timezone"""
    result = await session.execute(select(Timezone).where(Timezone.id == tz_id))
    timezone = result.scalar_one_or_none()
    
    if not timezone:
        raise HTTPException(404, "Timezone not found")
    
    await session.delete(timezone)
    await session.commit()
    return {"success": True}


@router.get("/api/timezones/active")
async def get_active_timezones_api(
    session: AsyncSession = Depends(get_db)
):
    """
    API endpoint to get active timezones.
    Used by web booking interface.
    """
    result = await session.execute(
        select(Timezone)
        .where(Timezone.is_active == True)
        .order_by(Timezone.sort_order, Timezone.offset_minutes)
    )
    timezones = result.scalars().all()
    
    return {
        "timezones": [
            {
                "id": tz.id,
                "offset_str": tz.offset_str,
                "offset_minutes": tz.offset_minutes,
                "display_name": tz.display_name
            }
            for tz in timezones
        ]
    }


# ============================================================================
# SLOT MANAGEMENT
# ============================================================================

@router.get("/slots", response_class=HTMLResponse)
async def admin_slots_page(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Slot management page"""
    # Get all future slots
    result = await session.execute(
        select(Slot)
        .where(Slot.start_time > datetime.utcnow())
        .order_by(Slot.start_time)
        .limit(50)
    )
    slots = result.scalars().all()
    
    # Get active timezones for slot creation form
    tz_result = await session.execute(
        select(Timezone)
        .where(Timezone.is_active == True)
        .order_by(Timezone.sort_order)
    )
    timezones = tz_result.scalars().all()
    
    return templates.TemplateResponse(
        "admin/slots.html",
        {
            "request": request,
            "slots": slots,
            "timezones": timezones
        }
    )


@router.post("/slots/create")
async def create_slot_api(
    date: str = Form(...),  # YYYY-MM-DD
    start_time: str = Form(...),  # HH:MM
    end_time: str = Form(...),  # HH:MM
    timezone: str = Form(...),  # UTC+X
    is_online: bool = Form(True),
    session: AsyncSession = Depends(get_db)
):
    """Create a new slot"""
    try:
        # Parse timezone
        offset_minutes = parse_utc_offset(timezone)
        if offset_minutes is None:
            raise HTTPException(400, "Invalid timezone format")
        
        # Parse datetime
        start_dt_local = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt_local = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        
        # Handle midnight crossing
        if end_dt_local <= start_dt_local:
            end_dt_local += timedelta(days=1)
        
        # Convert to UTC
        start_utc = user_tz_to_utc(start_dt_local, offset_minutes)
        end_utc = user_tz_to_utc(end_dt_local, offset_minutes)
        
        # Validate
        is_valid, error_msg = validate_slot_time(start_utc, end_utc)
        if not is_valid:
            raise HTTPException(400, error_msg)
        
        # Check overlap
        has_overlap = await check_slot_overlap(session, start_utc, end_utc, is_online)
        if has_overlap:
            raise HTTPException(400, "Slot overlaps with existing slot")
        
        # Create slot
        slot = Slot(
            start_time=start_utc,
            end_time=end_utc,
            is_online=is_online,
            status=SlotStatus.AVAILABLE
        )
        session.add(slot)
        await session.commit()
        await session.refresh(slot)
        
        return {"success": True, "slot_id": slot.id}
        
    except ValueError as e:
        raise HTTPException(400, f"Invalid date/time format: {e}")


@router.post("/slots/{slot_id}/delete")
async def delete_slot(
    slot_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Delete a slot (only if available)"""
    result = await session.execute(select(Slot).where(Slot.id == slot_id))
    slot = result.scalar_one_or_none()
    
    if not slot:
        raise HTTPException(404, "Slot not found")
    
    if slot.status != SlotStatus.AVAILABLE:
        raise HTTPException(400, "Cannot delete booked or held slot")
    
    await session.delete(slot)
    await session.commit()
    
    return {"success": True}


# ============================================================================
# REQUEST MANAGEMENT
# ============================================================================

@router.get("/requests", response_class=HTMLResponse)
async def admin_requests_page(
    request: Request,
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """View all booking requests"""
    query = select(BookingRequest).order_by(BookingRequest.created_at.desc())
    
    if status:
        try:
            status_enum = RequestStatus[status.upper()]
            query = query.where(BookingRequest.status == status_enum)
        except KeyError:
            pass
    
    result = await session.execute(query.limit(100))
    requests = result.scalars().all()
    
    return templates.TemplateResponse(
        "admin/requests.html",
        {
            "request": request,
            "requests": requests,
            "current_status": status
        }
    )


@router.get("/requests/{request_id}", response_class=HTMLResponse)
async def admin_request_detail(
    request: Request,
    request_id: int,
    session: AsyncSession = Depends(get_db)
):
    """View single request with negotiation history"""
    result = await session.execute(
        select(BookingRequest).where(BookingRequest.id == request_id)
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(404, "Request not found")
    
    # Get negotiation history
    history_result = await session.execute(
        select(Negotiation)
        .where(Negotiation.request_id == request_id)
        .order_by(Negotiation.timestamp)
    )
    history = history_result.scalars().all()
    
    # Get slot if linked
    slot = None
    if booking.slot_id:
        slot_result = await session.execute(select(Slot).where(Slot.id == booking.slot_id))
        slot = slot_result.scalar_one_or_none()
    
    return templates.TemplateResponse(
        "admin/request_detail.html",
        {
            "request": request,
            "booking": booking,
            "history": history,
            "slot": slot
        }
    )


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Approve a booking request"""
    result = await session.execute(
        select(BookingRequest).where(BookingRequest.id == request_id)
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(404, "Request not found")
    
    booking.status = RequestStatus.CONFIRMED
    
    # If slot linked, mark as booked
    if booking.slot_id:
        slot_result = await session.execute(select(Slot).where(Slot.id == booking.slot_id))
        slot = slot_result.scalar_one_or_none()
        if slot:
            slot.status = SlotStatus.BOOKED
    
    await session.commit()
    
    return {"success": True}


@router.post("/requests/{request_id}/reject")
async def reject_request(
    request_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Reject a booking request"""
    result = await session.execute(
        select(BookingRequest).where(BookingRequest.id == request_id)
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(404, "Request not found")
    
    booking.status = RequestStatus.REJECTED
    
    # Release slot if linked
    if booking.slot_id:
        slot_result = await session.execute(select(Slot).where(Slot.id == booking.slot_id))
        slot = slot_result.scalar_one_or_none()
        if slot:
            slot.status = SlotStatus.AVAILABLE
    
    await session.commit()
    
    return {"success": True}


# ============================================================================
# SETTINGS MANAGEMENT
# ============================================================================

@router.get("/settings", response_class=HTMLResponse)
async def admin_settings_page(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Settings management page"""
    result = await session.execute(select(Settings).where(Settings.id == 1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = Settings(id=1)
        session.add(settings)
        await session.commit()
    
    return templates.TemplateResponse(
        "admin/settings.html",
        {
            "request": request,
            "settings": settings
        }
    )


@router.post("/settings/update")
async def update_settings(
    availability_on: bool = Form(...),
    individual_price: str = Form(...),
    couple_price: str = Form(...),
    reminder_24h_enabled: bool = Form(False),
    reminder_1h_enabled: bool = Form(False),
    cancel_window_hours: int = Form(24),
    session: AsyncSession = Depends(get_db)
):
    """Update settings"""
    result = await session.execute(select(Settings).where(Settings.id == 1))
    settings = result.scalar_one()
    
    settings.availability_on = availability_on
    settings.individual_price = individual_price
    settings.couple_price = couple_price
    settings.reminder_24h_enabled = reminder_24h_enabled
    settings.reminder_1h_enabled = reminder_1h_enabled
    settings.cancel_window_hours = cancel_window_hours
    
    await session.commit()
    
    return {"success": True}


# ============================================================================
# TRANSLATIONS MANAGEMENT
# ============================================================================

@router.get("/translations", response_class=HTMLResponse)
async def admin_translations_page(
    request: Request,
    lang: str = "ru",
    session: AsyncSession = Depends(get_db)
):
    """Translations editor"""
    result = await session.execute(
        select(Translation)
        .where(Translation.lang == lang)
        .order_by(Translation.key)
    )
    translations = result.scalars().all()
    
    # Get all available languages
    lang_result = await session.execute(select(Translation.lang).distinct())
    languages = [row[0] for row in lang_result.all()]
    
    return templates.TemplateResponse(
        "admin/translations.html",
        {
            "request": request,
            "translations": translations,
            "current_lang": lang,
            "languages": languages
        }
    )


@router.post("/translations/update")
async def update_translation(
    lang: str = Form(...),
    key: str = Form(...),
    value: str = Form(...),
    session: AsyncSession = Depends(get_db)
):
    """Update a translation"""
    result = await session.execute(
        select(Translation).where(Translation.lang == lang, Translation.key == key)
    )
    translation = result.scalar_one_or_none()
    
    if translation:
        translation.value = value
    else:
        translation = Translation(lang=lang, key=key, value=value)
        session.add(translation)
    
    await session.commit()
    
    # Reload translations cache (if bot is running)
    from app.translations import refresh_translations_cache
    await refresh_translations_cache()
    
    return {"success": True}


# ============================================================================
# LANDING PAGES MANAGEMENT
# ============================================================================

@router.get("/landings", response_class=HTMLResponse)
async def admin_landings_page(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Landing pages management interface"""
    import os
    from pathlib import Path
    
    landings_dir = Path("/app/landings")
    landings = []
    
    # Define topic and language mappings
    topics = {
        "work_terms": "Work Terms",
        "qualification": "Qualification",
        "about_psychotherapy": "About Psychotherapy",
        "references": "References"
    }
    
    languages = {
        "ru": "Russian (Русский)",
        "am": "Armenian (Հայdelays)"
    }
    
    # Get all available languages from database
    lang_result = await session.execute(select(Translation.lang).distinct())
    db_languages = [row[0] for row in lang_result.all()]
    for lang_code in db_languages:
        if lang_code not in languages:
            languages[lang_code] = lang_code.upper()
    
    # Scan for existing landing files
    if landings_dir.exists():
        for file in landings_dir.glob("*.html"):
            # Parse filename: topic_lang.html
            parts = file.stem.split('_')
            if len(parts) >= 2:
                lang = parts[-1]
                topic = '_'.join(parts[:-1])
                
                stat = file.stat()
                landings.append({
                    "topic": topic,
                    "lang": lang,
                    "topic_display": topics.get(topic, topic),
                    "lang_display": languages.get(lang, lang),
                    "size": len(file.read_text(encoding='utf-8')),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                })
    
    return templates.TemplateResponse(
        "admin/landings.html",
        {
            "request": request,
            "landings": landings,
            "languages": languages
        }
    )


@router.post("/landings/upload")
async def upload_landing(
    topic: str = Form(...),
    lang: str = Form(...),
    content: str = Form(...)
):
    """Upload or update a landing page"""
    import os
    
    # Validate topic
    valid_topics = ["work_terms", "qualification", "about_psychotherapy", "references"]
    if topic not in valid_topics:
        raise HTTPException(400, "Invalid topic")
    
    # Validate content length
    if len(content) > 4000:
        raise HTTPException(400, "Content too long (max 4000 characters)")
    
    # Ensure landings directory exists
    os.makedirs("/app/landings", exist_ok=True)
    
    # Save file
    filename = f"/app/landings/{topic}_{lang}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return {"success": True, "filename": f"{topic}_{lang}.html"}


@router.get("/landings/get")
async def get_landing(topic: str, lang: str):
    """Get landing content for editing"""
    import os
    
    filename = f"/app/landings/{topic}_{lang}.html"
    if not os.path.exists(filename):
        raise HTTPException(404, "Landing not found")
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return {"topic": topic, "lang": lang, "content": content}


@router.post("/landings/update")
async def update_landing(
    topic: str = Form(...),
    lang: str = Form(...),
    content: str = Form(...)
):
    """Update existing landing"""
    import os
    
    filename = f"/app/landings/{topic}_{lang}.html"
    if not os.path.exists(filename):
        raise HTTPException(404, "Landing not found")
    
    if len(content) > 4000:
        raise HTTPException(400, "Content too long (max 4000 characters)")
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return {"success": True}


@router.post("/landings/delete")
async def delete_landing(topic: str, lang: str):
    """Delete a landing page"""
    import os
    
    filename = f"/app/landings/{topic}_{lang}.html"
    if not os.path.exists(filename):
        raise HTTPException(404, "Landing not found")
    
    os.remove(filename)
    return {"success": True}


# ============================================================================
# LANGUAGE MANAGEMENT
# ============================================================================

@router.get("/languages", response_class=HTMLResponse)
async def admin_languages_page(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Language management interface"""
    from app.translations import TEXTS_DEFAULTS
    
    # Get current languages from database
    result = await session.execute(
        select(Translation.lang).distinct()
    )
    current_languages = [row[0] for row in result.all()]
    
    # Get translation counts per language
    translation_counts = {}
    for lang in current_languages:
        count_result = await session.execute(
            select(func.count(Translation.id)).where(Translation.lang == lang)
        )
        translation_counts[lang] = count_result.scalar()
    
    # Get required keys from defaults
    required_keys = list(TEXTS_DEFAULTS.get('ru', {}).keys())
    
    language_names = {
        "ru": "Russian (Русский)",
        "am": "Armenian (Հdelays)",
        "en": "English",
        "de": "German (Deutsch)",
        "fr": "French (Français)",
        "es": "Spanish (Español)"
    }
    
    return templates.TemplateResponse(
        "admin/languages.html",
        {
            "request": request,
            "current_languages": current_languages,
            "translation_counts": translation_counts,
            "required_keys": required_keys,
            "language_names": language_names
        }
    )


@router.post("/languages/add")
async def add_language(
    lang_code: str = Form(...),
    lang_name: str = Form(...),
    clone_from: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_db)
):
    """Add a new language to the system"""
    from app.translations import TEXTS_DEFAULTS
    
    # Validate language code format
    if not lang_code.islower() or len(lang_code) != 2:
        raise HTTPException(400, "Language code must be 2 lowercase letters")
    
    # Check if language already exists
    result = await session.execute(
        select(Translation).where(Translation.lang == lang_code).limit(1)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, f"Language '{lang_code}' already exists")
    
    # Get source translations
    if clone_from and clone_from in TEXTS_DEFAULTS:
        source_translations = TEXTS_DEFAULTS[clone_from]
    else:
        # Use Russian as base template
        source_translations = TEXTS_DEFAULTS.get('ru', {})
    
    # Create translations for new language
    count = 0
    for key, value in source_translations.items():
        # If cloning, use the source value; otherwise use empty placeholder
        translation_value = value if clone_from else f"[{lang_code.upper()}] {key}"
        
        translation = Translation(
            lang=lang_code,
            key=key,
            value=translation_value
        )
        session.add(translation)
        count += 1
    
    await session.commit()
    
    # Reload cache
    from app.translations import refresh_translations_cache
    await refresh_translations_cache()
    
    return {
        "success": True,
        "lang_code": lang_code,
        "lang_name": lang_name,
        "translations_added": count
    }


@router.get("/languages/get-keys")
async def get_language_keys(
    lang: str,
    session: AsyncSession = Depends(get_db)
):
    """Get all translation keys for a language"""
    from app.translations import TEXTS_DEFAULTS
    
    # Get all required keys from defaults
    required_keys = list(TEXTS_DEFAULTS.get('ru', {}).keys())
    
    # Get current values for this language
    result = await session.execute(
        select(Translation).where(Translation.lang == lang)
    )
    current_translations = {t.key: t.value for t in result.scalars().all()}
    
    # Build response
    keys = []
    for key in required_keys:
        keys.append({
            "key": key,
            "current_value": current_translations.get(key, "")
        })
    
    return {"lang": lang, "keys": keys}


@router.post("/languages/bulk-update")
async def bulk_update_translations(
    data: dict,
    session: AsyncSession = Depends(get_db)
):
    """Bulk update translations for a language"""
    lang = data.get("lang")
    translations = data.get("translations", {})
    
    if not lang or not translations:
        raise HTTPException(400, "Missing lang or translations")
    
    updated_count = 0
    for key, value in translations.items():
        # Check if translation exists
        result = await session.execute(
            select(Translation).where(
                Translation.lang == lang,
                Translation.key == key
            )
        )
        translation = result.scalar_one_or_none()
        
        if translation:
            translation.value = value
        else:
            translation = Translation(lang=lang, key=key, value=value)
            session.add(translation)
        
        updated_count += 1
    
    await session.commit()
    
    return {"success": True, "updated_count": updated_count}


@router.post("/languages/reload-cache")
async def reload_translations_cache():
    """Reload translation cache from database"""
    from app.translations import refresh_translations_cache
    await refresh_translations_cache()
    return {"success": True, "message": "Translation cache reloaded"}
