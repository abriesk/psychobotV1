# app/web/routers/admin.py - v1.0.1 with timezone management
"""
Admin routes for slot management, request handling, settings, landings, languages, and timezones.
Protected by Nginx Proxy Manager Basic Auth.
"""
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import Optional
import re

from app.models import (
    Slot, SlotStatus, Request as BookingRequest, RequestStatus,
    Settings, Translation, Negotiation, SenderType, DEFAULT_TIMEZONE_OPTIONS
)
from app.utils_slots import (
    parse_utc_offset, user_tz_to_utc, validate_slot_time,
    check_slot_overlap, format_slot_time
)
from app.web.dependencies import get_db

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
# SLOT MANAGEMENT
# ============================================================================

@router.get("/slots", response_class=HTMLResponse)
async def admin_slots_page(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Slot management page"""
    result = await session.execute(
        select(Slot)
        .where(Slot.start_time > datetime.utcnow())
        .order_by(Slot.start_time)
        .limit(50)
    )
    slots = result.scalars().all()
    
    return templates.TemplateResponse(
        "admin/slots.html",
        {"request": request, "slots": slots}
    )


@router.post("/slots/create")
async def create_slot_api(
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    timezone: str = Form(...),
    is_online: bool = Form(True),
    session: AsyncSession = Depends(get_db)
):
    """Create a new slot"""
    try:
        offset_minutes = parse_utc_offset(timezone)
        if offset_minutes is None:
            raise HTTPException(400, "Invalid timezone format")
        
        start_dt_local = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt_local = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        
        if end_dt_local <= start_dt_local:
            end_dt_local += timedelta(days=1)
        
        start_utc = user_tz_to_utc(start_dt_local, offset_minutes)
        end_utc = user_tz_to_utc(end_dt_local, offset_minutes)
        
        is_valid, error_msg = validate_slot_time(start_utc, end_utc)
        if not is_valid:
            raise HTTPException(400, error_msg)
        
        has_overlap = await check_slot_overlap(session, start_utc, end_utc, is_online)
        if has_overlap:
            raise HTTPException(400, "Slot overlaps with existing slot")
        
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
        {"request": request, "requests": requests, "current_status": status}
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
        {"request": request, "settings": settings}
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
# TIMEZONE MANAGEMENT (v1.0.1 NEW)
# ============================================================================

@router.get("/timezones", response_class=HTMLResponse)
async def admin_timezones_page(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Timezone management page"""
    result = await session.execute(select(Settings).where(Settings.id == 1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = Settings(id=1)
        session.add(settings)
        await session.commit()
    
    timezones = settings.timezone_options or DEFAULT_TIMEZONE_OPTIONS
    
    # Sort by order
    timezones = sorted(timezones, key=lambda x: x.get('order', 999))
    
    return templates.TemplateResponse(
        "admin/timezones.html",
        {"request": request, "timezones": timezones}
    )


@router.post("/timezones/add")
async def add_timezone(
    code: str = Form(...),
    label_ru: str = Form(...),
    label_am: str = Form(""),
    emoji: str = Form("🌍"),
    order: int = Form(1),
    session: AsyncSession = Depends(get_db)
):
    """Add a new timezone option"""
    # Validate code format
    code = code.strip().upper()
    if not re.match(r'^UTC[+-]\d{1,2}(:\d{2})?$', code):
        raise HTTPException(400, "Invalid timezone format. Use UTC+X or UTC-X")
    
    # Validate code is parseable
    if parse_utc_offset(code) is None:
        raise HTTPException(400, "Invalid timezone offset")
    
    # Get current settings
    result = await session.execute(select(Settings).where(Settings.id == 1))
    settings = result.scalar_one()
    
    timezones = settings.timezone_options or []
    
    # Check for duplicate
    if any(tz['code'] == code for tz in timezones):
        raise HTTPException(400, f"Timezone {code} already exists")
    
    # Add new timezone
    new_tz = {
        "code": code,
        "label": {"ru": label_ru.strip()},
        "emoji": emoji.strip() or "🌍",
        "order": order
    }
    
    if label_am.strip():
        new_tz["label"]["am"] = label_am.strip()
    
    timezones.append(new_tz)
    
    # Sort by order
    timezones = sorted(timezones, key=lambda x: x.get('order', 999))
    
    # Save
    settings.timezone_options = timezones
    await session.commit()
    
    return {"success": True, "code": code}


@router.post("/timezones/update")
async def update_timezone(
    original_code: str = Form(...),
    code: str = Form(...),
    label_ru: str = Form(...),
    label_am: str = Form(""),
    emoji: str = Form("🌍"),
    order: int = Form(1),
    session: AsyncSession = Depends(get_db)
):
    """Update an existing timezone"""
    code = code.strip().upper()
    original_code = original_code.strip().upper()
    
    if not re.match(r'^UTC[+-]\d{1,2}(:\d{2})?$', code):
        raise HTTPException(400, "Invalid timezone format")
    
    result = await session.execute(select(Settings).where(Settings.id == 1))
    settings = result.scalar_one()
    
    timezones = settings.timezone_options or []
    
    # Find and update
    found = False
    for tz in timezones:
        if tz['code'] == original_code:
            tz['code'] = code
            tz['label'] = {"ru": label_ru.strip()}
            if label_am.strip():
                tz['label']['am'] = label_am.strip()
            tz['emoji'] = emoji.strip() or "🌍"
            tz['order'] = order
            found = True
            break
    
    if not found:
        raise HTTPException(404, "Timezone not found")
    
    # Sort and save
    settings.timezone_options = sorted(timezones, key=lambda x: x.get('order', 999))
    await session.commit()
    
    return {"success": True}


@router.post("/timezones/delete")
async def delete_timezone(
    code: str,
    session: AsyncSession = Depends(get_db)
):
    """Delete a timezone option"""
    result = await session.execute(select(Settings).where(Settings.id == 1))
    settings = result.scalar_one()
    
    timezones = settings.timezone_options or []
    original_count = len(timezones)
    
    # Filter out the timezone
    timezones = [tz for tz in timezones if tz['code'] != code]
    
    if len(timezones) == original_count:
        raise HTTPException(404, "Timezone not found")
    
    if len(timezones) == 0:
        raise HTTPException(400, "Cannot delete last timezone. Add another first.")
    
    settings.timezone_options = timezones
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
    
    return templates.TemplateResponse(
        "admin/translations.html",
        {
            "request": request,
            "translations": translations,
            "current_lang": lang,
            "languages": ["ru", "am"]
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
    
    topics = {
        "work_terms": "Work Terms",
        "qualification": "Qualification",
        "about_psychotherapy": "About Psychotherapy",
        "references": "References"
    }
    
    languages = {"ru": "Russian (Русский)", "am": "Armenian (Հայdelays)"}
    
    lang_result = await session.execute(select(Translation.lang).distinct())
    db_languages = [row[0] for row in lang_result.all()]
    for lang_code in db_languages:
        if lang_code not in languages:
            languages[lang_code] = lang_code.upper()
    
    if landings_dir.exists():
        for file in landings_dir.glob("*.html"):
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
        {"request": request, "landings": landings, "languages": languages}
    )


@router.post("/landings/upload")
async def upload_landing(
    topic: str = Form(...),
    lang: str = Form(...),
    content: str = Form(...)
):
    """Upload or update a landing page"""
    import os
    
    valid_topics = ["work_terms", "qualification", "about_psychotherapy", "references"]
    if topic not in valid_topics:
        raise HTTPException(400, "Invalid topic")
    
    if len(content) > 4000:
        raise HTTPException(400, "Content too long (max 4000 characters)")
    
    os.makedirs("/app/landings", exist_ok=True)
    
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
    
    result = await session.execute(select(Translation.lang).distinct())
    current_languages = [row[0] for row in result.all()]
    
    translation_counts = {}
    for lang in current_languages:
        count_result = await session.execute(
            select(func.count(Translation.id)).where(Translation.lang == lang)
        )
        translation_counts[lang] = count_result.scalar()
    
    required_keys = list(TEXTS_DEFAULTS.get('ru', {}).keys())
    
    language_names = {
        "ru": "Russian (Русский)",
        "am": "Armenian (Հայdelays)",
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
    
    if not lang_code.islower() or len(lang_code) != 2:
        raise HTTPException(400, "Language code must be 2 lowercase letters")
    
    result = await session.execute(
        select(Translation).where(Translation.lang == lang_code).limit(1)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, f"Language '{lang_code}' already exists")
    
    if clone_from and clone_from in TEXTS_DEFAULTS:
        source_translations = TEXTS_DEFAULTS[clone_from]
    else:
        source_translations = TEXTS_DEFAULTS.get('ru', {})
    
    count = 0
    for key, value in source_translations.items():
        translation_value = value if clone_from else f"[{lang_code.upper()}] {key}"
        translation = Translation(lang=lang_code, key=key, value=translation_value)
        session.add(translation)
        count += 1
    
    await session.commit()
    
    from app.translations import refresh_translations_cache
    await refresh_translations_cache()
    
    return {"success": True, "lang_code": lang_code, "lang_name": lang_name, "translations_added": count}


@router.get("/languages/get-keys")
async def get_language_keys(
    lang: str,
    session: AsyncSession = Depends(get_db)
):
    """Get all translation keys for a language"""
    from app.translations import TEXTS_DEFAULTS
    
    required_keys = list(TEXTS_DEFAULTS.get('ru', {}).keys())
    
    result = await session.execute(select(Translation).where(Translation.lang == lang))
    current_translations = {t.key: t.value for t in result.scalars().all()}
    
    keys = [{"key": key, "current_value": current_translations.get(key, "")} for key in required_keys]
    
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
        result = await session.execute(
            select(Translation).where(Translation.lang == lang, Translation.key == key)
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
