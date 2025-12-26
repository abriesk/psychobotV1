"""
User-side negotiation handlers for responding to admin proposals
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from app.db import AsyncSessionLocal
from app.models import Request, RequestStatus, Negotiation, SenderType, User
from app.translations import get_text
from sqlalchemy import select
import os

# Conversation state
USER_COUNTER_INPUT = 1

# 🔧 HELPER: Get user language
async def get_user_language(user_id):
    """Fetch user's language preference from database"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user.language if user else os.getenv('DEFAULT_LANGUAGE', 'ru')

# 🔧 HELPER: Notify admins
async def notify_admins(context, text, reply_markup=None, parse_mode="HTML"):
    """Send notification to all admins with proper error handling"""
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if not admin_ids_str:
        print("Warning: No admin IDs configured")
        return
    
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

# 🔧 NEW: User accepts admin proposal
async def user_negotiation_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user accepting the admin's proposal"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data: usr_yes_{req_id}
    parts = query.data.split('_')
    if len(parts) < 3:
        await query.edit_message_text("Error: Invalid callback data.")
        return
    
    req_id = int(parts[2])
    user_id = update.effective_user.id
    
    async with AsyncSessionLocal() as session:
        # Fetch request
        result = await session.execute(select(Request).where(Request.id == req_id))
        req = result.scalar_one_or_none()
        
        if not req:
            await query.edit_message_text("Error: Request not found.")
            return
        
        # Get the last admin proposal from negotiation history
        hist_result = await session.execute(
            select(Negotiation)
            .where(Negotiation.request_id == req_id, Negotiation.sender == SenderType.ADMIN)
            .order_by(Negotiation.timestamp.desc())
        )
        last_proposal = hist_result.scalars().first()
        
        # Log user acceptance
        acceptance_msg = get_text(await get_user_language(user_id), "btn_agree")
        neg = Negotiation(request_id=req_id, sender=SenderType.CLIENT, message=acceptance_msg)
        session.add(neg)
        
        # Update request status
        req.status = RequestStatus.CONFIRMED
        # Set final time from last proposal if available
        if last_proposal:
            req.final_time = last_proposal.message
        await session.commit()
        
        # Get user language
        user_lang = await get_user_language(user_id)
        
        # Notify user
        final_time = req.final_time or req.desired_time or "TBD"
        confirmation_msg = (
            get_text(user_lang, "status_confirmed") + "\n" +
            get_text(user_lang, "negotiation_agreed", time=final_time)
        )
        await query.edit_message_text(confirmation_msg)
        
        # Notify admins
        admin_notification = (
            f"✅ <b>Request Confirmed</b>\n"
            f"UUID: <code>{req.request_uuid}</code>\n"
            f"User: {user_id}\n"
            f"Type: {req.type.value}\n"
            f"Final Time: {final_time}\n"
            f"Status: Client accepted proposal"
        )
        await notify_admins(context, admin_notification)

# 🔧 NEW: User wants to counter-propose
async def user_negotiation_counter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start conversation for user counter-proposal"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data: usr_counter_{req_id}
    parts = query.data.split('_')
    if len(parts) < 3:
        await query.edit_message_text("Error: Invalid callback data.")
        return ConversationHandler.END
    
    req_id = int(parts[2])
    user_id = update.effective_user.id
    
    # Store in context for next step
    context.user_data['counter_req_id'] = req_id
    
    # Get user language
    user_lang = await get_user_language(user_id)
    
    # Ask for counter-proposal
    await query.message.reply_text(
        get_text(user_lang, "ask_time")  # Reuse translation for "write desired time"
    )
    
    return USER_COUNTER_INPUT

# 🔧 NEW: Handle user counter-proposal text
async def user_negotiation_counter_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user's counter-proposal text input"""
    req_id = context.user_data.get('counter_req_id')
    if not req_id:
        await update.message.reply_text("Error: No active negotiation found.")
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    counter_text = update.message.text
    
    async with AsyncSessionLocal() as session:
        # Fetch request
        result = await session.execute(select(Request).where(Request.id == req_id))
        req = result.scalar_one_or_none()
        
        if not req:
            await update.message.reply_text("Error: Request not found.")
            return ConversationHandler.END
        
        # Log user counter-proposal
        neg = Negotiation(request_id=req_id, sender=SenderType.CLIENT, message=counter_text)
        session.add(neg)
        
        # Keep status as NEGOTIATING
        req.status = RequestStatus.NEGOTIATING
        await session.commit()
        
        # Get user language
        user_lang = await get_user_language(user_id)
        
        # Confirm to user
        await update.message.reply_text(
            get_text(user_lang, "confirm_sent")
        )
        
        # Notify admins with action buttons
        admin_notification = (
            f"💬 <b>Counter-Proposal from Client</b>\n"
            f"UUID: <code>{req.request_uuid}</code>\n"
            f"User: {user_id}\n"
            f"Type: {req.type.value}\n"
            f"Counter-Proposal: {counter_text}\n\n"
            f"Original Request: {req.desired_time or 'N/A'}"
        )
        
        btns = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve_{req.id}")],
            [InlineKeyboardButton("💬 Propose Alt", callback_data=f"adm_prop_{req.id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"adm_reject_{req.id}")]
        ]
        
        await notify_admins(
            context, 
            admin_notification, 
            reply_markup=InlineKeyboardMarkup(btns)
        )
    
    # Clear context
    context.user_data.pop('counter_req_id', None)
    return ConversationHandler.END