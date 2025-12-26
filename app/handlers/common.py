from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from sqlalchemy import select
from app.db import AsyncSessionLocal
from app.models import User
from app.translations import get_text
import os

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Determine default logic
    kb = [
        [KeyboardButton("Русский"), KeyboardButton("Հայերեն")]
    ]
    await update.message.reply_text(
        "Выберите язык / Ընտրեք լեզուն",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return 1 # Wait for language

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lang = 'ru'
    if 'Հայերեն' in text:
        lang = 'am'
    
    user_id = update.effective_user.id
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=user_id, language=lang)
            session.add(user)
        else:
            user.language = lang
        await session.commit()
    
    await show_main_menu(update, context, lang)
    return ConversationHandler.END

async def show_main_menu(update, context, lang):
    menu = [
        [get_text(lang, "menu_consultation")],
        [get_text(lang, "menu_terms"), get_text(lang, "menu_qual")],
        [get_text(lang, "menu_about")],
        [get_text(lang, "menu_home")]
     ]
    await update.message.reply_text(
        get_text(lang, "welcome"),
        reply_markup=ReplyKeyboardMarkup(menu, resize_keyboard=True)
    )

async def back_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        # Use existing language or fallback to env
        lang = user.language if user else os.getenv('DEFAULT_LANGUAGE', 'ru')

    # Send a small confirmation and show the main menu
    await update.message.reply_text(get_text(lang, "welcome_back"))
    await show_main_menu(update, context, lang)

    # If this was called inside a ConversationHandler, return ConversationHandler.END
    return ConversationHandler.END

async def handle_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        lang = user.language if user else os.getenv('DEFAULT_LANGUAGE')

    text = update.message.text
    topic_map = {
        get_text(lang, "menu_terms"): "work_terms",
        get_text(lang, "menu_qual"): "qualification",
        get_text(lang, "menu_about"): "about_psychotherapy"
    }

    if text in topic_map:
        topic = topic_map[text]
        path = f"/app/landings/{topic}_{lang}.html"
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            await update.message.reply_html(content)
        else:
            await update.message.reply_text(get_text(lang, "file_not_found"))