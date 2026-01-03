# app/web/routers/client.py - UPDATED with landing content
"""
Public routes for client booking interface.
No authentication required.
"""
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional
from pathlib import Path

from app.models import Slot, SlotStatus, Request as BookingRequest, RequestType, RequestStatus, User
from app.utils_slots import (
    parse_utc_offset, get_available_slots, format_slot_time,
    hold_slot, confirm_slot_booking
)
from app.web.dependencies import get_db
from app.translations import get_text
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


# ============================================================================
# PAGE ROUTES
# ============================================================================

@router.get("/", response_class=HTMLResponse)
async def client_index(request: Request, lang: str = "ru"):
    """
    Client landing page with content from uploaded landings.
    Displays work terms, qualification, about psychotherapy, and references.
    """
    landings_dir = Path("/app/landings")
    landing_content = {}
    
    # Define topics to display
    topics = {
        "work_terms": {
            "ru": "Условия работы",
            "am": "Աշխատանքի պայմաններ",
            "en": "Work Terms"
        },
        "qualification": {
            "ru": "Квалификация",
            "am": "Որակավորում",
            "en": "Qualification"
        },
        "about_psychotherapy": {
            "ru": "О психотерапии",
            "am": "Հոգեթերապիայի մասին",
            "en": "About Psychotherapy"
        },
        "references": {
            "ru": "Рекомендации",
            "am": "Հղումներ",
            "en": "References"
        }
    }
    
    # Load landing content for selected language
    for topic_key in topics.keys():
        file_path = landings_dir / f"{topic_key}_{lang}.html"
        if file_path.exists():
            try:
                content = file_path.read_text(encoding='utf-8')
                landing_content[topic_key] = {
                    "title": topics[topic_key].get(lang, topic_key),
                    "content": content
                }
            except Exception as e:
                print(f"Error reading landing {topic_key}_{lang}: {e}")
    
    return templates.TemplateResponse(
        "client/index.html",
        {
            "request": request,
            "lang": lang,
            "landings": landing_content,
            "languages": {
                "ru": "Русский",
                "am": "Հայերեն"
            },
            "has_content": len(landing_content) > 0
        }
    )


@router.get("/book", response_class=HTMLResponse)
async def booking_page(request: Request, lang: str = "ru"):
    """Client booking page"""
    return templates.TemplateResponse(
        "client/book.html",
        {
            "request": request,
            "lang": lang,
            "languages": {"ru": "Русский", "am": "Հայերեն"}
        }
    )


@router.get("/booking/success", response_class=HTMLResponse)
async def booking_success(request: Request, uuid: str, lang: str = "ru"):
    """Booking confirmation page"""
    return templates.TemplateResponse(
        "client/success.html",
        {
            "request": request,
            "lang": lang,
            "booking_uuid": uuid
        }
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/api/slots/available")
async def get_available_slots_api(
    is_online: bool = True,
    timezone_offset: str = "UTC+4",
    limit: int = 10,
    session: AsyncSession = Depends(get_db)
):
    """
    Get available slots for booking.
    
    Query params:
    - is_online: true for online, false for onsite
    - timezone_offset: User's timezone (e.g., UTC+4)
    - limit: Max number of slots to return
    """
    # Parse timezone offset
    offset_minutes = parse_utc_offset(timezone_offset)
    if offset_minutes is None:
        raise HTTPException(400, "Invalid timezone offset format")
    
    # Get available slots
    slots = await get_available_slots(
        session,
        is_online=is_online,
        limit=limit
    )
    
    # Format for response
    slots_data = []
    for slot in slots:
        slots_data.append({
            "id": slot.id,
            "start_time_utc": slot.start_time.isoformat(),
            "end_time_utc": slot.end_time.isoformat(),
            "display_time": format_slot_time(slot, offset_minutes),
            "is_online": slot.is_online,
            "duration_minutes": int((slot.end_time - slot.start_time).total_seconds() / 60)
        })
    
    return {"slots": slots_data, "timezone": timezone_offset}


@router.post("/api/booking/submit")
async def submit_booking(
    slot_id: int = Form(...),
    consultation_type: str = Form(...),  # "individual" or "couple"
    timezone: str = Form(...),
    problem: str = Form(None),
    contact_method: str = Form(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Submit a booking request.
    
    This holds the slot and creates a pending request.
    Admin will confirm via Telegram or web admin panel.
    """
    # Validate consultation type
    try:
        req_type = RequestType.INDIVIDUAL if consultation_type == "individual" else RequestType.COUPLE
    except:
        raise HTTPException(400, "Invalid consultation type")
    
    # Hold the slot
    success, message = await hold_slot(session, slot_id)
    if not success:
        raise HTTPException(400, f"Cannot hold slot: {message}")
    
    # Create booking request
    request_uuid = str(uuid.uuid4())
    
    # Note: We don't have user_id from web (no Telegram), use placeholder
    # Admin will see this is a web booking
    booking = BookingRequest(
        request_uuid=request_uuid,
        user_id=0,  # Placeholder for web bookings
        type=req_type,
        timezone=timezone,
        problem=problem,
        preferred_comm=contact_method,
        status=RequestStatus.PENDING,
        slot_id=slot_id
    )
    
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    
    # Get slot details for response
    slot_result = await session.execute(select(Slot).where(Slot.id == slot_id))
    slot = slot_result.scalar_one()
    
    offset_minutes = parse_utc_offset(timezone)
    slot_time = format_slot_time(slot, offset_minutes if offset_minutes else 0)
    
    return {
        "success": True,
        "request_uuid": request_uuid,
        "slot_time": slot_time,
        "message": "Booking request submitted. You will be contacted for confirmation."
    }


@router.get("/api/translations/{lang}")
async def get_translations(lang: str):
    """
    Get all translations for a language.
    Used by client-side JS for dynamic text.
    """
    # Common keys needed by web interface
    keys = [
        "menu_consultation", "menu_terms", "menu_qual", "menu_about",
        "btn_individual", "btn_couple", "btn_online", "btn_onsite",
        "ask_timezone", "ask_time", "ask_problem", "ask_comm",
        "confirm_sent", "error_generic"
    ]
    
    translations = {}
    for key in keys:
        translations[key] = get_text(lang, key)
    
    return {"lang": lang, "translations": translations}
