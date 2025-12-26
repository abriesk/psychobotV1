# app/scheduler.py - Periodic jobs for slot management
"""
Background jobs for slot system:
- Ghost slot cleanup (expired holds)
- Future: Reminders (Priority 6)
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import AsyncSessionLocal
from app.utils_slots import release_expired_holds


# Initialize scheduler (will be started by main.py)
scheduler = AsyncIOScheduler()


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
    
    logging.info("📅 Scheduler jobs registered:")
    logging.info("   - cleanup_expired_holds: every 5 minutes")
    
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
            logging.info(f"?? Auto-rejected {len(old_requests)} stale PENDING requests")