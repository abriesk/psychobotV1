# app/handlers/consultation.py - v1.0.1 with timezone button selection
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from app.db import AsyncSessionLocal
from app.models import User, Request, RequestType, RequestStatus, DEFAULT_TIMEZONE_OPTIONS
from app.utils import get_settings
from app.translations import get_text
from sqlalchemy import select
from app.models import Slot, SlotStatus
from app.utils_slots import (
    parse_utc_offset, get_available_slots, format_slot_time,
    hold_slot, confirm_slot_booking, release_hold
)
import os

# States
TYPE_SELECT, TIMEZONE, TIME, PROBLEM, CONTACTS, WAITLIST_CONTACTS = range(6)
SLOT_SELECT = 6  # State for slot selection (after timezone)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_home_keyboard(lang):
    """Returns a keyboard with just the Home button"""
    return ReplyKeyboardMarkup(
        [[get_text(lang, "menu_home")]], 
        resize_keyboard=True
    )

def get_main_menu_keyboard(lang):
    """Returns the full main menu keyboard"""
    menu = [
        [get_text(lang, "menu_consultation")],
        [get_text(lang, "menu_terms"), get_text(lang, "menu_qual")],
        [get_text(lang, "menu_about")],
        [get_text(lang, "menu_home")]
    ]
    return ReplyKeyboardMarkup(menu, resize_keyboard=True)


def build_timezone_buttons(timezone_options: list, lang: str) -> list:
    """
    Build InlineKeyboardButtons from timezone_options JSON.
    
    Args:
        timezone_options: List of timezone dicts from Settings
        lang: User's language code
    
    Returns:
        List of button rows for InlineKeyboardMarkup
    """
    # Sort by order if present
    sorted_options = sorted(timezone_options, key=lambda x: x.get('order', 999))
    
    buttons = []
    row = []
    
    for tz in sorted_options:
        # Get label in user's language, fallback to ru, then to code
        labels = tz.get('label', {})
        label = labels.get(lang) or labels.get('ru') or tz['code']
        
        emoji = tz.get('emoji', '🌍')
        code = tz['code']
        
        button_text = f"{emoji} {label} ({code})"
        button = InlineKeyboardButton(button_text, callback_data=f"tz_{code}")
        
        row.append(button)
        
        # 2 buttons per row
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    # Add remaining button if odd number
    if row:
        buttons.append(row)
    
    return buttons


# ============================================================================
# CONSULTATION FLOW
# ============================================================================

async def start_consultation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for consultation booking"""
    user_id = update.effective_user.id
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        lang = user.language if user else os.getenv('DEFAULT_LANGUAGE', 'ru')
        settings = await get_settings(session)
    
    context.user_data['lang'] = lang
    
    if not settings.availability_on:
        # Waitlist flow
        await update.message.reply_text(get_text(lang, "waitlist_intro"))
        await update.message.reply_text(
            get_text(lang, "ask_problem"),
            reply_markup=get_home_keyboard(lang)
        )
        
        # Send references landing if exists
        path = f"/app/landings/references_{lang}.html"
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                await update.message.reply_html(f.read())
                
        return WAITLIST_CONTACTS
    else:
        # Active booking flow
        kb = [
            [get_text(lang, "btn_online"), get_text(lang, "btn_onsite")],
            [get_text(lang, "menu_home")]
        ]
        await update.message.reply_text(
            get_text(lang, "menu_consultation"),
            reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
        )
        return TYPE_SELECT


async def type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle online/onsite selection"""
    lang = context.user_data.get('lang', 'ru')
    text = update.message.text
    
    async with AsyncSessionLocal() as session:
        settings = await get_settings(session)
    
    if text == get_text(lang, "btn_onsite"):
        link = os.getenv("CLINIC_ONSITE_LINK")
        await update.message.reply_text(f"Link: {link}", reply_markup=get_main_menu_keyboard(lang))
        return ConversationHandler.END
    
    # Online selected
    context.user_data['is_online'] = True
    
    # Ask consultation type: Individual vs Couple
    btn_ind = get_text(lang, "btn_individual", price=settings.individual_price)
    btn_cpl = get_text(lang, "btn_couple", price=settings.couple_price)
    
    kb = [[btn_ind], [btn_cpl], [get_text(lang, "menu_home")]]
    await update.message.reply_text(
        "Type?", 
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return TIMEZONE


async def timezone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show timezone selection buttons (fetched from DB)"""
    lang = context.user_data.get('lang', 'ru')
    text = update.message.text
    
    # Determine consultation type from button text
    # Check for keywords that indicate individual consultation
    individual_keywords = ["Individual", "Индивидуальная", "60"]
    if any(kw in text for kw in individual_keywords):
        context.user_data['req_type'] = RequestType.INDIVIDUAL
    else:
        context.user_data['req_type'] = RequestType.COUPLE
    
    # Fetch timezone options from database
    async with AsyncSessionLocal() as session:
        settings = await get_settings(session)
        timezone_options = settings.timezone_options or DEFAULT_TIMEZONE_OPTIONS
    
    # Build timezone buttons
    tz_buttons = build_timezone_buttons(timezone_options, lang)
    
    # Timezone prompt (use translation if available)
    tz_prompt = get_text(lang, "ask_timezone") or "🌍 Select your timezone:"
    if not tz_prompt.startswith("🌍"):
        tz_prompt = "🌍 <b>" + tz_prompt + "</b>"
    
    await update.message.reply_text(
        tz_prompt,
        reply_markup=InlineKeyboardMarkup(tz_buttons),
        parse_mode="HTML"
    )
    return SLOT_SELECT


async def timezone_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle timezone button selection, then show available slots"""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data.get('lang', 'ru')
    
    # Extract timezone from callback data (e.g., "tz_UTC+4" -> "UTC+4")
    tz_str = query.data.replace("tz_", "")
    
    # Parse and validate UTC offset
    offset = parse_utc_offset(tz_str)
    if offset is None:
        await query.edit_message_text("❌ Invalid timezone. Please try again.")
        return SLOT_SELECT
    
    # Store timezone
    context.user_data['timezone'] = tz_str
    context.user_data['tz_offset'] = offset
    
    # Get available slots
    is_online = context.user_data.get('is_online', True)
    
    async with AsyncSessionLocal() as session:
        slots = await get_available_slots(
            session,
            is_online=is_online,
            limit=10
        )
        
        if not slots:
            # No slots available → fallback to text input
            no_slots_msg = (
                f"✅ Timezone: {tz_str}\n\n"
                "⚠️ No slots available at this time.\n\n"
                "Please enter your desired date and time:"
            )
            
            await query.edit_message_text(no_slots_msg)
            return TIME
        
        # Build slot buttons
        buttons = []
        for slot in slots:
            slot_text = format_slot_time(slot, offset)
            callback_data = f"slot_{slot.id}"
            buttons.append([InlineKeyboardButton(f"📅 {slot_text}", callback_data=callback_data)])
        
        # Add "other time" option
        buttons.append([InlineKeyboardButton("⏰ Other time (free text)", callback_data="slot_other")])
        
        select_slot_msg = (
            f"✅ Timezone: {tz_str}\n\n"
            f"📅 <b>Available slots:</b>\n\n"
            "Select a time:"
        )
        
        await query.edit_message_text(
            select_slot_msg,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )
        
        return PROBLEM


async def slot_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle slot selection button click"""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data.get('lang', 'ru')
    
    if query.data == "slot_other":
        # User wants to enter time manually
        await query.edit_message_text("⏰ Please enter your desired date and time:")
        context.user_data['slot_fallback'] = True
        return TIME
    
    # Extract slot ID
    slot_id = int(query.data.replace("slot_", ""))
    
    # Hold the slot (15-minute reservation)
    async with AsyncSessionLocal() as session:
        success, message = await hold_slot(session, slot_id)
        
        if not success:
            await query.edit_message_text(
                f"❌ {message}\n\nSlot no longer available. Please select another."
            )
            return SLOT_SELECT
        
        # Store selected slot
        context.user_data['selected_slot_id'] = slot_id
        
        # Get slot details
        result = await session.execute(select(Slot).where(Slot.id == slot_id))
        slot = result.scalar_one()
        
        tz_offset = context.user_data.get('tz_offset', 0)
        slot_time_str = format_slot_time(slot, tz_offset)
        
        held_msg = (
            f"✅ <b>Slot reserved!</b>\n\n"
            f"📅 {slot_time_str}\n\n"
            f"⏰ You have 15 minutes to complete booking.\n\n"
            f"{get_text(lang, 'ask_problem')}"
        )
        
        await query.edit_message_text(held_msg, parse_mode="HTML")
        
        return PROBLEM


async def time_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text time input (fallback when no slots or user chose 'other')"""
    context.user_data['desired_time'] = update.message.text
    lang = context.user_data.get('lang', 'ru')
    
    await update.message.reply_text(
        get_text(lang, "ask_problem"),
        reply_markup=get_home_keyboard(lang)
    )
    return CONTACTS


async def problem_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle problem description input"""
    context.user_data['problem'] = update.message.text
    lang = context.user_data.get('lang', 'ru')
    
    # Ask for preferred communication method
    await update.message.reply_text(
        get_text(lang, "ask_comm"),
        reply_markup=get_home_keyboard(lang)
    )
    return CONTACTS


async def contacts_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finalize request and confirm slot booking"""
    context.user_data['preferred_comm'] = update.message.text
    lang = context.user_data.get('lang', 'ru')
    
    # Get problem from context (may have been set in different steps)
    problem = context.user_data.get('problem', '')
    
    async with AsyncSessionLocal() as session:
        req = Request(
            user_id=update.effective_user.id,
            type=context.user_data.get('req_type', RequestType.INDIVIDUAL),
            timezone=context.user_data.get('timezone'),
            desired_time=context.user_data.get('desired_time'),
            problem=problem,
            preferred_comm=context.user_data.get('preferred_comm'),
            status=RequestStatus.PENDING
        )
        
        # Handle slot-based booking
        selected_slot_id = context.user_data.get('selected_slot_id')
        if selected_slot_id:
            session.add(req)
            await session.commit()
            await session.refresh(req)
            
            success, message = await confirm_slot_booking(session, selected_slot_id, req.id)
            
            if not success:
                await update.message.reply_text(f"❌ Booking failed: {message}")
                return ConversationHandler.END
            
            # Get confirmed slot details
            result = await session.execute(select(Slot).where(Slot.id == selected_slot_id))
            slot = result.scalar_one()
            tz_offset = context.user_data.get('tz_offset', 0)
            slot_time_str = format_slot_time(slot, tz_offset)
            
            confirm_msg = (
                f"✅ <b>Booking confirmed!</b>\n\n"
                f"📅 {slot_time_str}\n"
                f"🆔 Request ID: <code>{req.request_uuid[:8]}</code>\n\n"
                f"You will be contacted to confirm details."
            )
            
            await update.message.reply_text(confirm_msg, parse_mode="HTML")
            
        else:
            # Text-based booking (fallback)
            session.add(req)
            await session.commit()
            await session.refresh(req)
            
            await update.message.reply_text(get_text(lang, "confirm_sent"))
        
        # Notify admin
        admin_text = (
            f"📋 <b>New Booking Request</b>\n\n"
            f"🆔 UUID: <code>{req.request_uuid}</code>\n"
            f"👤 User: {update.effective_user.id}\n"
            f"📝 Type: {req.type.value}\n"
            f"🌍 TZ: {req.timezone or 'N/A'}\n"
            f"{'📅 Slot-based' if selected_slot_id else '📝 Text-based'}\n"
            f"💬 Problem: {(req.problem or 'N/A')[:100]}"
        )
        
        btns = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve_{req.id}")],
            [InlineKeyboardButton("💬 Propose Alt", callback_data=f"adm_prop_{req.id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"adm_reject_{req.id}")]
        ]
        
        admin_ids = os.getenv("ADMIN_IDS", "")
        if admin_ids:
            for admin_id in admin_ids.split(","):
                try:
                    await context.bot.send_message(
                        chat_id=int(admin_id.strip()),
                        text=admin_text,
                        reply_markup=InlineKeyboardMarkup(btns),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Failed to notify admin {admin_id}: {e}")
    
    # Clear context and return to main menu
    context.user_data.clear()
    
    await update.message.reply_text(
        get_text(lang, "welcome_back"),
        reply_markup=get_main_menu_keyboard(lang)
    )
    return ConversationHandler.END


async def waitlist_finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finalize waitlist request"""
    lang = context.user_data.get('lang', 'ru')
    text = update.message.text
    
    async with AsyncSessionLocal() as session:
        req = Request(
            user_id=update.effective_user.id,
            type=RequestType.WAITLIST,
            problem=text,
            status=RequestStatus.PENDING
        )
        session.add(req)
        await session.commit()
        
        # Notify Admin
        admin_text = f"⏳ <b>Waitlist Add</b>\nUser: {update.effective_user.id}\nData: {text}"
        
        admin_ids = os.getenv("ADMIN_IDS", "")
        if admin_ids:
            for admin_id in admin_ids.split(","):
                try:
                    await context.bot.send_message(
                        chat_id=int(admin_id.strip()), 
                        text=admin_text, 
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Failed to notify admin {admin_id}: {e}")

    await update.message.reply_text(
        get_text(lang, "confirm_sent"),
        reply_markup=get_main_menu_keyboard(lang)
    )
    return ConversationHandler.END
