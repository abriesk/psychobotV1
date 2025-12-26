from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from app.db import AsyncSessionLocal
from app.models import User, Request, RequestType, RequestStatus
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
SLOT_SELECT = 6  # New state for slot selection

# 🔧 HELPER: Create home keyboard with lang
def get_home_keyboard(lang):
    """Returns a keyboard with just the Home button"""
    return ReplyKeyboardMarkup(
        [[get_text(lang, "menu_home")]], 
        resize_keyboard=True
    )

# 🔧 NEW HELPER: Get main menu keyboard
def get_main_menu_keyboard(lang):
    """Returns the full main menu keyboard"""
    menu = [
        [get_text(lang, "menu_consultation")],
        [get_text(lang, "menu_terms"), get_text(lang, "menu_qual")],
        [get_text(lang, "menu_about")],
        [get_text(lang, "menu_home")]
    ]
    return ReplyKeyboardMarkup(menu, resize_keyboard=True)

async def start_consultation(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        # 🔧 CHANGED: Add home button to waitlist flow
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
        # Active flow
        kb = [[get_text(lang, "btn_online"), get_text(lang, "btn_onsite")],[get_text(lang, "menu_home")]]
        await update.message.reply_text(
            get_text(lang, "menu_consultation"),
            reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
        )
        return TYPE_SELECT

async def type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    # Ask Type: Individual vs Couple
    btn_ind = get_text(lang, "btn_individual", price=settings.individual_price)
    btn_cpl = get_text(lang, "btn_couple", price=settings.couple_price)
    
    kb = [[btn_ind], [btn_cpl], [get_text(lang, "menu_home")]]
    await update.message.reply_text(
        "Type?", 
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return TIMEZONE

async def timezone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for user's timezone, then show available slots"""
    lang = context.user_data.get('lang', 'ru')
    text = update.message.text
    
    # Determine consultation type
    if "Individual" in text or "Индивидуальная" in text or "Անհատական" in text:
        context.user_data['req_type'] = RequestType.INDIVIDUAL
    else:
        context.user_data['req_type'] = RequestType.COUPLE
    
    # Ask for timezone (UTC offset format)
    tz_prompt = {
        'ru': (
            "🌍 <b>Ваш часовой пояс</b>\n\n"
            "Укажите ваш UTC часовой пояс.\n\n"
            "Формат: UTC+X или UTC-X\n\n"
            "Примеры:\n"
            "• UTC+4 (Ереван)\n"
            "• UTC+3 (Москва)\n"
            "• UTC+2 (Киев)\n"
            "• UTC-5 (Нью-Йорк)"
        ),
        'am': (
            "🌍 <b>Ձեր ժամային գոտին</b>\n\n"
            "Նշեք ձեր UTC ժամային գոտին.\n\n"
            "Ֆորմատ: UTC+X կամ UTC-X\n\n"
            "Օրինակներ:\n"
            "• UTC+4 (Երևան)\n"
            "• UTC+3 (Մոսկվա)"
        )
    }.get(lang, "Enter your timezone (UTC+X or UTC-X):")
    
    await update.message.reply_text(
        tz_prompt,
        reply_markup=get_home_keyboard(lang),
        parse_mode="HTML"
    )
    return SLOT_SELECT


async def slot_select_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse timezone and show available slots"""
    lang = context.user_data.get('lang', 'ru')
    tz_str = update.message.text.strip()
    
    # Parse UTC offset
    offset = parse_utc_offset(tz_str)
    if offset is None:
        error_msg = {
            'ru': "❌ Неверный формат часового пояса.\n\nИспользуйте: UTC+4 или UTC-5",
            'am': "❌ Սխալ ժամային գոտու ձևաչափ.\n\nՕգտագործեք: UTC+4 կամ UTC-5"
        }.get(lang, "Invalid timezone format. Use: UTC+4 or UTC-5")
        
        await update.message.reply_text(error_msg)
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
            no_slots_msg = {
                'ru': (
                    "⚠️ К сожалению, сейчас нет доступных слотов.\n\n"
                    "Вы можете:\n"
                    "1. Указать желаемое время свободным текстом\n"
                    "2. Вернуться позже\n\n"
                    "Укажите желаемое время и дату:"
                ),
                'am': (
                    "⚠️ Ցավոք, այս պահին հասանելի սլոթեր չկան։\n\n"
                    "Կարող եք:\n"
                    "1. Նշել ցանկալի ժամանակը ազատ տեքստով\n"
                    "2. Վերադառնալ ավելի ուշ\n\n"
                    "Նշեք ցանկալի ժամանակն ու ամսաթիվը:"
                )
            }.get(lang, "No slots available. Please enter your desired time:")
            
            await update.message.reply_text(
                no_slots_msg,
                reply_markup=get_home_keyboard(lang)
            )
            # Continue to old flow (text input)
            return TIME
        
        # Build slot buttons
        buttons = []
        for slot in slots:
            slot_text = format_slot_time(slot, offset)
            callback_data = f"slot_{slot.id}"
            buttons.append([InlineKeyboardButton(f"📅 {slot_text}", callback_data=callback_data)])
        
        # Add "other time" option
        other_time_text = {
            'ru': "⏰ Другое время (свободный текст)",
            'am': "⏰ Այլ ժամանակ (ազատ տեքստ)"
        }.get(lang, "Other time (free text)")
        buttons.append([InlineKeyboardButton(other_time_text, callback_data="slot_other")])
        
        select_slot_msg = {
            'ru': f"✅ Часовой пояс: {tz_str}\n\n📅 <b>Доступные слоты:</b>\n\nВыберите удобное время:",
            'am': f"✅ Ժամային գոտի: {tz_str}\n\n📅 <b>Հասանելի սլոթեր:</b>\n\nԸնտրեք հարմար ժամանակ:"
        }.get(lang, f"Timezone: {tz_str}\n\nAvailable slots:")
        
        await update.message.reply_text(
            select_slot_msg,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )
        
        return PROBLEM  # Will handle via callback


async def slot_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle slot selection button click"""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data.get('lang', 'ru')
    
    if query.data == "slot_other":
        # User wants to enter time manually
        other_time_prompt = {
            'ru': "⏰ Укажите желаемое время и дату свободным текстом:",
            'am': "⏰ Նշեք ցանկալի ժամանակն ու ամսաթիվը:"
        }.get(lang, "Enter your desired time:")
        
        await query.edit_message_text(other_time_prompt)
        context.user_data['slot_fallback'] = True
        return TIME
    
    # Extract slot ID
    slot_id = int(query.data.replace("slot_", ""))
    
    # Hold the slot (15-minute reservation)
    async with AsyncSessionLocal() as session:
        success, message = await hold_slot(session, slot_id)
        
        if not success:
            error_msg = {
                'ru': f"❌ {message}\n\nСлот больше не доступен. Выберите другой:",
                'am': f"❌ {message}\n\nՍլոթը այլևս հասանելի չէ։ Ընտրեք այլ:"
            }.get(lang, f"Error: {message}")
            
            await query.edit_message_text(error_msg)
            # Show slots again
            return SLOT_SELECT
        
        # Store selected slot
        context.user_data['selected_slot_id'] = slot_id
        
        # Get slot details
        result = await session.execute(select(Slot).where(Slot.id == slot_id))
        slot = result.scalar_one()
        
        tz_offset = context.user_data.get('tz_offset', 0)
        slot_time_str = format_slot_time(slot, tz_offset)
        
        held_msg = {
            'ru': (
                f"✅ <b>Слот зарезервирован!</b>\n\n"
                f"📅 {slot_time_str}\n\n"
                f"⏰ У вас есть 15 минут, чтобы завершить запись.\n\n"
                f"{get_text(lang, 'ask_problem')}"
            ),
            'am': (
                f"✅ <b>Սլոթը ամրագրված է!</b>\n\n"
                f"📅 {slot_time_str}\n\n"
                f"⏰ Ձեզ մոտ 15 րոպե կա ամրագրումն ավարտելու համար։\n\n"
                f"{get_text(lang, 'ask_problem')}"
            )
        }.get(lang, f"Slot held: {slot_time_str}\n\n{get_text(lang, 'ask_problem')}")
        
        await query.edit_message_text(held_msg, parse_mode="HTML")
        
        return PROBLEM

async def time_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timezone'] = update.message.text
    lang = context.user_data.get('lang', 'ru')
    
    # 🔧 CHANGED: Keep home button visible
    await update.message.reply_text(
        get_text(lang, "ask_time"),
        reply_markup=get_home_keyboard(lang)
    )
    return PROBLEM

async def problem_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['desired_time'] = update.message.text
    lang = context.user_data.get('lang', 'ru')
    
    # 🔧 CHANGED: Keep home button visible
    await update.message.reply_text(
        get_text(lang, "ask_problem"),
        reply_markup=get_home_keyboard(lang)
    )
    return CONTACTS

async def contacts_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finalize request and confirm slot booking"""
    context.user_data['problem'] = update.message.text
    lang = context.user_data.get('lang', 'ru')
    
    # Create request
    async with AsyncSessionLocal() as session:
        req = Request(
            user_id=update.effective_user.id,
            type=context.user_data['req_type'],
            timezone=context.user_data.get('timezone'),
            desired_time=context.user_data.get('desired_time'),  # May be None if slot-based
            problem=context.user_data['problem'],
            status=RequestStatus.PENDING
        )
        
        # Handle slot-based booking
        selected_slot_id = context.user_data.get('selected_slot_id')
        if selected_slot_id:
            # Confirm slot booking (HELD → BOOKED)
            session.add(req)
            await session.commit()
            await session.refresh(req)
            
            success, message = await confirm_slot_booking(session, selected_slot_id, req.id)
            
            if not success:
                # Slot booking failed (expired hold, etc.)
                error_msg = {
                    'ru': f"❌ Не удалось забронировать слот: {message}",
                    'am': f"❌ Չհաջողվեց ամրագրել սլոթը: {message}"
                }.get(lang, f"Booking failed: {message}")
                
                await update.message.reply_text(error_msg)
                return ConversationHandler.END
            
            # Get confirmed slot details
            result = await session.execute(select(Slot).where(Slot.id == selected_slot_id))
            slot = result.scalar_one()
            tz_offset = context.user_data.get('tz_offset', 0)
            slot_time_str = format_slot_time(slot, tz_offset)
            
            confirm_msg = {
                'ru': (
                    f"✅ <b>Запись подтверждена!</b>\n\n"
                    f"📅 {slot_time_str}\n"
                    f"🆔 Номер заявки: {req.request_uuid}\n\n"
                    f"Я свяжусь с вами для подтверждения деталей."
                ),
                'am': (
                    f"✅ <b>Ամրագրումը հաստատված է!</b>\n\n"
                    f"📅 {slot_time_str}\n"
                    f"🆔 Հայտի համար: {req.request_uuid}\n\n"
                    f"Ես կկապնվեմ ձեզ հետ՝ մանրամասները հաստատելու համար։"
                )
            }.get(lang, f"Booking confirmed!\n{slot_time_str}\nRequest: {req.request_uuid}")
            
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
            f"UUID: <code>{req.request_uuid}</code>\n"
            f"Type: {req.type.value}\n"
            f"{'Slot-based' if selected_slot_id else 'Text-based'}\n"
            f"Problem: {req.problem[:100] if req.problem else 'N/A'}"
        )
        
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
        get_text(lang, "welcome_back"),
        reply_markup=get_main_menu_keyboard(lang)
    )
    return ConversationHandler.END

async def waitlist_finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'ru')
    problem = context.user_data.get('temp_problem', 'No details')
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
        
        # 🔧 FIXED: Convert admin_id to int and handle errors
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
        #reply_markup=ReplyKeyboardRemove()  # Remove for final message
    )
    return ConversationHandler.END

# Waitlist entry captures problem then contacts
async def waitlist_capture_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_problem'] = update.message.text
    lang = context.user_data.get('lang', 'ru')
    
    # 🔧 CHANGED: Keep home button visible
    await update.message.reply_text(
        get_text(lang, "waitlist_contacts"),
        reply_markup=get_home_keyboard(lang)
    )
    return WAITLIST_CONTACTS