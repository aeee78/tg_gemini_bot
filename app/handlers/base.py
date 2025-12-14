from aiogram import Router, F, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.requests import get_or_create_user, update_user_model, update_user_mode, toggle_search, set_whitelist
from app.keyboards.builders import get_main_keyboard, get_model_selection_keyboard
from app.config import config

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id)

    greeting = (
        f"👋 Привет! Я ваш персональный помощник на базе Google Gemini.\n\n"
        f"Текущие настройки:\n"
        f"🧠 Модель: *{config.MODEL_ALIASES.get(user.current_model, user.current_model)}*\n"
        f"✍️ Режим отправки: *{user.send_mode}*\n"
        f"🔎 Поиск Google: *{'Вкл' if user.search_enabled else 'Выкл'}*\n\n"
        f"Используйте /help для справки."
    )

    await message.answer(
        greeting,
        reply_markup=get_main_keyboard(user.current_model, user.send_mode, user.search_enabled),
        parse_mode="Markdown"
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "ℹ️ *Справка по боту*\n\n"
        "/start - Начать заново\n"
        "/unlock_pro <code> - Разблокировать Pro модели\n"
        "Плюс команды инструментов: /translate, /rewrite, /image и т.д.\n"
        "Отправьте фото или файлы для анализа."
    )
    await message.answer(help_text, parse_mode="Markdown")

@router.message(Command("unlock_pro"))
async def cmd_unlock_pro(message: types.Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == config.PRO_CODE:
        await set_whitelist(session, message.from_user.id, True)
        await message.reply("✅ Доступ к PRO моделям разблокирован!")
    else:
        await message.reply("❌ Неверный код.")
