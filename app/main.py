import logging
import os
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler
from telegram.ext import filters as tg_filters
from app.db import init_db
from app.handlers import common, consultation, admin, user_negotiation
from app.translations import load_translations_cache
from app.scheduler import start_scheduler, stop_scheduler, set_bot_instance  # Added set_bot_instance

# Import dynamic custom filters
import app.filters as custom_filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def post_init(application):
    """Initialize database and load translations cache"""
    await init_db()
    print("✅ Database initialized.")
    
    # Load translations from DB into memory cache
    await load_translations_cache()
    print("✅ Translation cache loaded - filters are now language-agnostic!")
    
    # Register bot instance for scheduler notifications (Web → Telegram bridge)
    set_bot_instance(application.bot)
    print("✅ Bot instance registered with scheduler for web notifications.")
    
    # Start scheduler for background jobs
    start_scheduler()
    print("✅ Scheduler started.")
    
async def post_shutdown(application):
    """Cleanup on bot shutdown"""
    stop_scheduler()
    print("✅ Scheduler stopped.")


async def cancel_any_conversation(update, context):
    """Universal conversation canceller - returns user to main menu"""
    from app.handlers.common import back_to_home
    return await back_to_home(update, context)
    
    
def main():
    token = os.getenv("BOT_TOKEN")
    app = (ApplicationBuilder()
           .token(token)
           .post_init(post_init)
           .post_shutdown(post_shutdown)
           .build())

    # ========================================================================
    # CONVERSATION HANDLERS - With language-agnostic filters
    # ========================================================================
    
    # --- Conversation: Start & Language ---
    lang_conv = ConversationHandler(
        entry_points=[CommandHandler("start", common.start)],
        states={
            1: [MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, common.set_language)]
        },
        fallbacks=[
            CommandHandler("cancel", common.start)
        ],
        per_user=True,
        per_chat=True,
        name="language_selection"
    )
    
    # --- Conversation: Consultation Booking ---
    # Uses custom_filters.booking_button (language-agnostic!)
    consult_conv = ConversationHandler(
        entry_points=[MessageHandler(custom_filters.booking_button, consultation.start_consultation)],
        states={
            consultation.TYPE_SELECT: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.home_button & ~custom_filters.admin_button_hardcoded, 
                    consultation.type_selected
                )
            ],
            consultation.TIMEZONE: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.home_button & ~custom_filters.admin_button_hardcoded, 
                    consultation.timezone_step
                )
            ],
            consultation.SLOT_SELECT: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.home_button & ~custom_filters.admin_button_hardcoded, 
                    consultation.slot_select_step
                )
            ],
            consultation.TIME: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.home_button & ~custom_filters.admin_button_hardcoded, 
                    consultation.time_step
                )
            ],
            consultation.PROBLEM: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.home_button & ~custom_filters.admin_button_hardcoded, 
                    consultation.problem_step
                )
            ],
            consultation.CONTACTS: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.home_button & ~custom_filters.admin_button_hardcoded, 
                    consultation.contacts_step
                )
            ],
            consultation.WAITLIST_CONTACTS: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.home_button & ~custom_filters.admin_button_hardcoded, 
                    consultation.waitlist_finalize
                )
            ],
        },
        fallbacks=[
            MessageHandler(custom_filters.home_button, common.back_to_home),
            MessageHandler(custom_filters.admin_button_hardcoded, cancel_any_conversation),
            CommandHandler("cancel", common.back_to_home),
            CallbackQueryHandler(consultation.slot_selected_callback, pattern="^slot_")
        ],
        per_user=True,
        per_chat=True,
        name="consultation_booking"
    )
    
    # --- Admin: Proposal Conversation ---
    admin_prop_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin.admin_propose_start, pattern="^adm_prop_")],
        states={
            "ADMIN_PROPOSE": [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.admin_button_hardcoded, 
                    admin.admin_propose_text
                )
            ]
        },
        fallbacks=[
            MessageHandler(custom_filters.home_button, common.back_to_home),
            MessageHandler(custom_filters.admin_button_hardcoded, cancel_any_conversation),
            CommandHandler("cancel", common.start)
        ],
        per_user=True,
        per_chat=True,
        name="admin_proposal"
    )

    # --- Landing Upload Conversation ---
    landing_upload_conv = ConversationHandler(
        entry_points=[MessageHandler(tg_filters.Regex("^Upload Landing$"), admin.upload_landing_start)],
        states={
            admin.UPLOAD_TOPIC: [
                CallbackQueryHandler(admin.upload_topic_selected, pattern="^upload_")
            ],
            admin.UPLOAD_LANG: [
                CallbackQueryHandler(admin.upload_lang_selected, pattern="^upload_")
            ],
            admin.UPLOAD_FILE: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.admin_button_hardcoded, 
                    admin.upload_text_received
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(admin.upload_landing_start, pattern="^upload_cancel$"),
            MessageHandler(custom_filters.admin_button_hardcoded, cancel_any_conversation),
            CommandHandler("cancel", common.start)
        ],
        per_user=True,
        per_chat=True,
        name="landing_upload"
    )

    # --- Price Edit Conversation ---
    price_edit_conv = ConversationHandler(
        entry_points=[MessageHandler(tg_filters.Regex("^Edit Prices$"), admin.edit_prices_start)],
        states={
            admin.EDIT_PRICE_TYPE: [
                CallbackQueryHandler(admin.edit_price_type_selected, pattern="^price_")
            ],
            admin.EDIT_PRICE_VALUE: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.admin_button_hardcoded, 
                    admin.edit_price_value_received
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(admin.edit_prices_start, pattern="^price_cancel$"),
            MessageHandler(custom_filters.admin_button_hardcoded, cancel_any_conversation),
            CommandHandler("cancel", common.start)
        ],
        per_user=True,
        per_chat=True,
        name="price_edit"
    )

    # --- User: Counter-Proposal Conversation ---
    user_counter_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(user_negotiation.user_negotiation_counter_start, pattern="^usr_counter_")],
        states={
            user_negotiation.USER_COUNTER_INPUT: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND, 
                    user_negotiation.user_negotiation_counter_text
                )
            ]
        },
        fallbacks=[
            MessageHandler(custom_filters.home_button, common.back_to_home),
            CommandHandler("cancel", common.start)
        ],
        per_user=True,
        per_chat=True,
        name="user_counter_proposal"
    )

    # --- Slot Creation Conversation (Admin) ---
    create_slot_conv = ConversationHandler(
        entry_points=[MessageHandler(tg_filters.Regex("^Create Slot$"), admin.create_slot_start)],
        states={
            admin.CREATE_SLOT_TYPE: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.admin_button_hardcoded, 
                    admin.create_slot_type_input
                )
            ],
            admin.CREATE_SLOT_DATE: [
                CallbackQueryHandler(admin.create_slot_date_callback, pattern="^slot_(online|onsite|cancel)$")
            ],
            admin.CREATE_SLOT_START: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.admin_button_hardcoded, 
                    admin.create_slot_start_input
                )
            ],
            admin.CREATE_SLOT_END: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.admin_button_hardcoded, 
                    admin.create_slot_end_input
                )
            ],
            admin.CREATE_SLOT_CONFIRM: [
                MessageHandler(
                    tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.admin_button_hardcoded, 
                    admin.create_slot_confirm_input
                )
            ]
        },
        fallbacks=[
            MessageHandler(custom_filters.admin_button_hardcoded, cancel_any_conversation),
            CommandHandler("cancel", common.start)
        ],
        per_user=True,
        per_chat=True,
        name="slot_creation"
    )

    # ========================================================================
    # HANDLER REGISTRATION - Order matters!
    # ========================================================================
    
    # Conversation handlers first (most specific)
    app.add_handler(lang_conv)
    app.add_handler(consult_conv)
    app.add_handler(admin_prop_conv)
    app.add_handler(landing_upload_conv)
    app.add_handler(price_edit_conv)
    app.add_handler(user_counter_conv)
    app.add_handler(create_slot_conv)
    
    # Admin commands (should work even during conversations due to filters above)
    app.add_handler(CommandHandler("admin", admin.admin_start))
    app.add_handler(CommandHandler("refresh_translations", admin.refresh_translations))
    app.add_handler(MessageHandler(tg_filters.Regex("^Toggle Availability$"), admin.toggle_availability))
    app.add_handler(MessageHandler(tg_filters.Regex("^Pending Requests$"), admin.list_pending))
    app.add_handler(MessageHandler(tg_filters.Regex("^View Slots$"), admin.view_slots))
    
    # Admin callbacks
    app.add_handler(CallbackQueryHandler(admin.admin_callback, pattern="^adm_(view|approve|reject)_"))
    app.add_handler(CallbackQueryHandler(admin.create_slot_overlap_callback, pattern="^slot_create_(yes|no)$"))
    
    # User negotiation callbacks
    app.add_handler(CallbackQueryHandler(user_negotiation.user_negotiation_yes, pattern="^usr_yes_"))
    
    # Main Menu Navigation (lowest priority)
    # Exclude all menu buttons to avoid conflicts
    app.add_handler(MessageHandler(
        tg_filters.TEXT & ~tg_filters.COMMAND & ~custom_filters.all_menu_buttons, 
        common.handle_menu_click
    ))

    # Home button handler (works from anywhere)
    app.add_handler(MessageHandler(custom_filters.home_button, common.back_to_home))

    print("✅ All handlers registered with language-agnostic filters")
    app.run_polling()

if __name__ == '__main__':
    main()
