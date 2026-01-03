# app/scheduler.py - Periodic jobs for slot management and notifications
"""
Background jobs for:
- Ghost slot cleanup (expired holds)
- Telegram notification delivery (web → bot bridge)
- Future: Reminders (Priority 6)
"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, and_
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from app.db import AsyncSessionLocal
from app.models import (
    Slot, SlotStatus, Request, RequestStatus,
    PendingNotification, NotificationType, User
)
from app.translations import get_text
from app.utils_slots import release_expired_holds


# Initialize scheduler (will be started by main.py)
scheduler = AsyncIOScheduler()

# Bot instance - set by main.py on startup
_bot_instance = None


def set_bot_instance(bot):
    """Called by main.py to provide bot reference for sending messages"""
    global _bot_instance
    _bot_instance = bot
    logging.info("✅ Bot instance registered with scheduler")


async def cleanup_expired_holds_job():
    """
    Periodic job to release expired slot holds.
    Runs every 5 minutes.
    """
    try:
        async with AsyncSessionLocal() as session:
            count = await release_expired_holds(session)
            if count > 0:
                logging.info(f"✅ Released {count} expired slot hold(s)")
    except Exception as e:
        logging.error(f"❌ Error in cleanup job: {e}")


async def process_pending_notifications_job():
    """
    Process pending notifications from web UI.
    Sends Telegram messages to users.
    Runs every 10 seconds.
    """
    global _bot_instance
    
    if not _bot_instance:
        return  # Bot not ready yet
    
    try:
        async with AsyncSessionLocal() as session:
            # Get pending notifications (not sent, less than 3 attempts)
            result = await session.execute(
                select(PendingNotification).where(
                    and_(
                        PendingNotification.sent_at.is_(None),
                        PendingNotification.attempts < 3
                    )
                ).order_by(PendingNotification.created_at).limit(10)
            )
            notifications = result.scalars().all()
            
            for notif in notifications:
                await send_telegram_notification(session, notif)
                
    except Exception as e:
        logging.error(f"❌ Error processing notifications: {e}")


async def send_telegram_notification(session, notif: PendingNotification):
    """Send a single notification via Telegram"""
    global _bot_instance
    
    try:
        notif.attempts += 1
        
        # Get user language
        user_result = await session.execute(
            select(User).where(User.id == notif.user_id)
        )
        user = user_result.scalar_one_or_none()
        lang = user.language if user else 'ru'
        
        # Build message based on type
        if notif.notification_type == NotificationType.PROPOSAL:
            # Admin proposal - include Accept/Counter buttons
            message_text = get_text(lang, "negotiation_new", msg=notif.message)
            
            buttons = [
                [InlineKeyboardButton(
                    get_text(lang, "btn_agree"), 
                    callback_data=f"usr_yes_{notif.request_id}"
                )],
                [InlineKeyboardButton(
                    get_text(lang, "btn_counter"), 
                    callback_data=f"usr_counter_{notif.request_id}"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            
        elif notif.notification_type == NotificationType.CONFIRMATION:
            message_text = get_text(lang, "status_confirmed")
            if notif.proposed_time:
                message_text += f"\n{get_text(lang, 'negotiation_agreed', time=notif.proposed_time)}"
            reply_markup = None
            
        elif notif.notification_type == NotificationType.REJECTION:
            message_text = get_text(lang, "negotiation_rejected")
            reply_markup = None
            
        else:
            # Custom/other
            message_text = notif.message
            reply_markup = None
        
        # Send via bot
        await _bot_instance.send_message(
            chat_id=notif.user_id,
            text=message_text,
            reply_markup=reply_markup
        )
        
        # Mark as sent
        notif.sent_at = datetime.utcnow()
        notif.error = None
        await session.commit()
        
        logging.info(f"📤 Sent {notif.notification_type.value} to user {notif.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        notif.error = error_msg
        await session.commit()
        logging.error(f"❌ Failed to send notification {notif.id}: {error_msg}")


async def cleanup_old_pending():
    """Auto-reject PENDING requests older than 48h"""
    async with AsyncSessionLocal() as session:
        cutoff = datetime.utcnow() - timedelta(hours=48)
        result = await session.execute(
            select(Request).where(
                Request.status == RequestStatus.PENDING,
                Request.created_at < cutoff
            )
        )
        old_requests = result.scalars().all()
        
        for req in old_requests:
            req.status = RequestStatus.REJECTED
            # Release slot if held
            if req.slot_id:
                slot_result = await session.execute(select(Slot).where(Slot.id == req.slot_id))
                slot = slot_result.scalar_one_or_none()
                if slot:
                    slot.status = SlotStatus.AVAILABLE
        
        await session.commit()
        if old_requests:
            logging.info(f"🧹 Auto-rejected {len(old_requests)} stale PENDING requests")


def start_scheduler():
    """
    Start all periodic jobs.
    Called by main.py on bot startup.
    """
    # Ghost slot cleanup: every 5 minutes
    scheduler.add_job(
        cleanup_expired_holds_job,
        trigger=IntervalTrigger(minutes=5),
        id='cleanup_expired_holds',
        name='Release expired slot holds',
        replace_existing=True
    )
    
    # Notification sender: every 10 seconds
    scheduler.add_job(
        process_pending_notifications_job,
        trigger=IntervalTrigger(seconds=10),
        id='process_notifications',
        name='Send pending Telegram notifications',
        replace_existing=True
    )
    
    # Stale request cleanup: every hour
    scheduler.add_job(
        cleanup_old_pending,
        trigger=IntervalTrigger(hours=1),
        id='cleanup_old_pending',
        name='Auto-reject stale pending requests',
        replace_existing=True
    )
    
    logging.info("📅 Scheduler jobs registered:")
    logging.info("   - cleanup_expired_holds: every 5 minutes")
    logging.info("   - process_notifications: every 10 seconds")
    logging.info("   - cleanup_old_pending: every hour")
    
    scheduler.start()
    logging.info("✅ Scheduler started")


def stop_scheduler():
    """
    Stop scheduler gracefully.
    Called on bot shutdown.
    """
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logging.info("⏹️  Scheduler stopped")
