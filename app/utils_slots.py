# app/utils_slots.py - Timezone and slot management utilities
"""
Utilities for slot-based booking system:
- UTC ↔ User timezone conversion
- Slot availability queries
- Hold mechanism management
"""
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Slot, SlotStatus, Request, RequestStatus


# ============================================================================
# TIMEZONE CONVERSION
# ============================================================================

def parse_utc_offset(offset_str: str) -> Optional[int]:
    """
    Parse UTC offset string to minutes.
    
    Args:
        offset_str: Format "UTC+4", "UTC-5:30", "GMT+3" etc.
    
    Returns:
        Offset in minutes from UTC, or None if invalid
    
    Examples:
        "UTC+4" -> 240
        "UTC-5:30" -> -330
        "GMT+0" -> 0
    """
    try:
        # Remove whitespace and convert to uppercase
        offset_str = offset_str.strip().upper()
        
        # Handle GMT/UTC prefix
        if offset_str.startswith('GMT'):
            offset_str = offset_str[3:]
        elif offset_str.startswith('UTC'):
            offset_str = offset_str[3:]
        else:
            return None
        
        # Parse sign
        if offset_str.startswith('+'):
            sign = 1
            offset_str = offset_str[1:]
        elif offset_str.startswith('-'):
            sign = -1
            offset_str = offset_str[1:]
        else:
            return None
        
        # Parse hours and optional minutes
        if ':' in offset_str:
            hours, minutes = offset_str.split(':')
            hours = int(hours)
            minutes = int(minutes)
        else:
            hours = int(offset_str)
            minutes = 0
        
        # Convert to minutes
        total_minutes = sign * (hours * 60 + minutes)
        
        # Validate range (-12:00 to +14:00)
        if -720 <= total_minutes <= 840:
            return total_minutes
        else:
            return None
            
    except (ValueError, AttributeError):
        return None


def utc_to_user_tz(utc_dt: datetime, offset_minutes: int) -> datetime:
    """
    Convert UTC datetime to user's timezone.
    
    Args:
        utc_dt: DateTime in UTC
        offset_minutes: User's UTC offset in minutes
    
    Returns:
        DateTime in user's timezone
    """
    return utc_dt + timedelta(minutes=offset_minutes)


def user_tz_to_utc(user_dt: datetime, offset_minutes: int) -> datetime:
    """
    Convert user's local datetime to UTC.
    
    Args:
        user_dt: DateTime in user's timezone
        offset_minutes: User's UTC offset in minutes
    
    Returns:
        DateTime in UTC
    """
    return user_dt - timedelta(minutes=offset_minutes)


def format_slot_time(slot: Slot, offset_minutes: int) -> str:
    """
    Format slot time for display in user's timezone.
    
    Args:
        slot: Slot object
        offset_minutes: User's UTC offset in minutes
    
    Returns:
        Formatted string like "Dec 25, 10:00-11:00 (your time)"
    """
    start_local = utc_to_user_tz(slot.start_time, offset_minutes)
    end_local = utc_to_user_tz(slot.end_time, offset_minutes)
    
    # Format: "Dec 25, 10:00-11:00"
    date_str = start_local.strftime("%b %d")
    start_time = start_local.strftime("%H:%M")
    end_time = end_local.strftime("%H:%M")
    
    return f"{date_str}, {start_time}-{end_time}"


# ============================================================================
# SLOT AVAILABILITY QUERIES
# ============================================================================

async def get_available_slots(
    session: AsyncSession,
    is_online: bool,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 10
) -> List[Slot]:
    """
    Get available slots for booking.
    
    Args:
        session: Database session
        is_online: True for online slots, False for onsite
        from_date: Start date filter (UTC)
        to_date: End date filter (UTC)
        limit: Maximum number of slots to return
    
    Returns:
        List of available slots, ordered by start_time
    """
    query = select(Slot).where(
        and_(
            Slot.status == SlotStatus.AVAILABLE,
            Slot.is_online == is_online,
            Slot.start_time > (from_date or datetime.utcnow())
        )
    )
    
    if to_date:
        query = query.where(Slot.start_time < to_date)
    
    query = query.order_by(Slot.start_time).limit(limit)
    
    result = await session.execute(query)
    return result.scalars().all()


# ============================================================================
# HOLD MECHANISM
# ============================================================================

HOLD_DURATION_MINUTES = 15


async def hold_slot(session: AsyncSession, slot_id: int) -> Tuple[bool, str]:
    """
    Place a temporary hold on a slot.
    
    Args:
        session: Database session
        slot_id: ID of slot to hold
    
    Returns:
        (success: bool, message: str)
    """
    # Fetch slot with lock
    result = await session.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    )
    slot = result.scalar_one_or_none()
    
    if not slot:
        return False, "Slot not found"
    
    if slot.status != SlotStatus.AVAILABLE:
        return False, "Slot no longer available"
    
    # Apply hold
    slot.status = SlotStatus.HELD
    slot.updated_at = datetime.utcnow()
    
    await session.commit()
    return True, "Slot held successfully"


async def release_hold(session: AsyncSession, slot_id: int) -> bool:
    """
    Release hold on a slot (make it available again).
    
    Args:
        session: Database session
        slot_id: ID of slot to release
    
    Returns:
        True if released, False if not held
    """
    result = await session.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    )
    slot = result.scalar_one_or_none()
    
    if not slot or slot.status != SlotStatus.HELD:
        return False
    
    slot.status = SlotStatus.AVAILABLE
    slot.updated_at = datetime.utcnow()
    await session.commit()
    return True


async def confirm_slot_booking(
    session: AsyncSession,
    slot_id: int,
    request_id: int
) -> Tuple[bool, str]:
    """
    Confirm slot booking (HELD -> BOOKED).
    
    Args:
        session: Database session
        slot_id: ID of slot to book
        request_id: ID of request booking this slot
    
    Returns:
        (success: bool, message: str)
    """
    # Fetch slot and request with locks
    slot_result = await session.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    )
    slot = slot_result.scalar_one_or_none()
    
    if not slot:
        return False, "Slot not found"
    
    if slot.status != SlotStatus.HELD:
        return False, "Slot must be held before booking"
    
    # Update slot
    slot.status = SlotStatus.BOOKED
    slot.updated_at = datetime.utcnow()
    
    # Update request
    request_result = await session.execute(
        select(Request).where(Request.id == request_id)
    )
    request = request_result.scalar_one_or_none()
    
    if request:
        request.slot_id = slot_id
        request.scheduled_datetime = slot.start_time
        request.status = RequestStatus.CONFIRMED
    
    await session.commit()
    return True, "Slot booked successfully"


async def release_expired_holds(session: AsyncSession) -> int:
    """
    Release all holds that have expired (>15 minutes old).
    Called by cleanup job.
    
    Args:
        session: Database session
    
    Returns:
        Number of slots released
    """
    cutoff = datetime.utcnow() - timedelta(minutes=HOLD_DURATION_MINUTES)
    
    # Find expired held slots
    result = await session.execute(
        select(Slot).where(
            and_(
                Slot.status == SlotStatus.HELD,
                Slot.updated_at < cutoff
            )
        )
    )
    expired_slots = result.scalars().all()
    
    # Release them
    count = 0
    for slot in expired_slots:
        slot.status = SlotStatus.AVAILABLE
        slot.updated_at = datetime.utcnow()
        count += 1
    
    if count > 0:
        await session.commit()
        print(f"🧹 Released {count} expired slot hold(s)")
    
    return count


# ============================================================================
# VALIDATION
# ============================================================================

def validate_slot_time(start_time: datetime, end_time: datetime) -> Tuple[bool, str]:
    """
    Validate slot time constraints.
    
    Args:
        start_time: Slot start (UTC)
        end_time: Slot end (UTC)
    
    Returns:
        (is_valid: bool, error_message: str)
    """
    now = datetime.utcnow()
    
    # Start must be in future
    if start_time <= now:
        return False, "Start time must be in the future"
    
    # End must be after start
    if end_time <= start_time:
        return False, "End time must be after start time"
    
    # Duration should be reasonable (15 min to 4 hours)
    duration = (end_time - start_time).total_seconds() / 60
    if duration < 15:
        return False, "Slot duration too short (minimum 15 minutes)"
    if duration > 240:
        return False, "Slot duration too long (maximum 4 hours)"
    
    return True, ""


async def check_slot_overlap(
    session: AsyncSession,
    start_time: datetime,
    end_time: datetime,
    is_online: bool,
    exclude_slot_id: Optional[int] = None
) -> bool:
    """
    Check if slot overlaps with existing slots.
    
    Args:
        session: Database session
        start_time: New slot start (UTC)
        end_time: New slot end (UTC)
        is_online: Online/onsite flag
        exclude_slot_id: Slot ID to exclude (for updates)
    
    Returns:
        True if overlap exists, False if no overlap
    """
    query = select(Slot).where(
        and_(
            Slot.is_online == is_online,
            # Overlap condition: (start1 < end2) AND (end1 > start2)
            Slot.start_time < end_time,
            Slot.end_time > start_time
        )
    )
    
    if exclude_slot_id:
        query = query.where(Slot.id != exclude_slot_id)
    
    result = await session.execute(query)
    overlapping = result.scalars().first()
    
    return overlapping is not None
