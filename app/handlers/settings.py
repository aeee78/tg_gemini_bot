from aiogram import Router, F, types
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.requests import get_or_create_user, update_user_model, update_user_mode, toggle_search, clear_history
from app.keyboards.builders import get_main_keyboard, get_model_selection_keyboard
from app.config import config

router = Router()

@router.message(F.text.startswith("Модель:"))
async def select_model_click(message: types.Message):
    await message.answer("Выберите модель:", reply_markup=get_model_selection_keyboard())

@router.callback_query(F.data.startswith("model_"))
async def model_selected(callback: types.CallbackQuery, session: AsyncSession):
    model_name = callback.data.replace("model_", "")
    user = await get_or_create_user(session, callback.from_user.id)

    # Check permissions
    if model_name in ["gemini-2.5-pro", "gemini-2.5-flash-image-preview"] and not user.is_whitelisted:
        await callback.answer("🔒 Нужен PRO доступ (/unlock_pro)", show_alert=True)
        return

    await update_user_model(session, user.telegram_id, model_name)
    await clear_history(session, user.telegram_id) # Switching model clears history context usually

    # Refresh user object to get new state
    user = await get_or_create_user(session, callback.from_user.id)

    await callback.message.edit_text(f"✅ Выбрана модель: {config.MODEL_ALIASES.get(model_name)}")
    await callback.message.answer(
        "Контекст очищен. Можете начинать диалог.",
        reply_markup=get_main_keyboard(user.current_model, user.send_mode, user.search_enabled)
    )

@router.message(F.text.startswith("Режим:"))
async def toggle_mode(message: types.Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id)
    new_mode = config.SEND_MODE_MANUAL if user.send_mode == config.SEND_MODE_IMMEDIATE else config.SEND_MODE_IMMEDIATE

    await update_user_mode(session, user.telegram_id, new_mode)

    msg = f"Режим изменен на: {new_mode}"
    if new_mode == config.SEND_MODE_MANUAL:
        msg += "\nСообщения будут накапливаться в буфере."

    await message.answer(
        msg,
        reply_markup=get_main_keyboard(user.current_model, new_mode, user.search_enabled)
    )

@router.message(F.text.startswith("Поиск:"))
async def toggle_search_click(message: types.Message, session: AsyncSession):
    is_enabled = await toggle_search(session, message.from_user.id)
    user = await get_or_create_user(session, message.from_user.id)

    status = "Вкл" if is_enabled else "Выкл"
    await message.answer(
        f"🔎 Поиск Google: {status}",
        reply_markup=get_main_keyboard(user.current_model, user.send_mode, is_enabled)
    )

@router.message(F.text == "Новый чат")
async def new_chat(message: types.Message, session: AsyncSession):
    await clear_history(session, message.from_user.id)
    user = await get_or_create_user(session, message.from_user.id)

    await message.answer(
        "🗑 Контекст диалога очищен.",
        reply_markup=get_main_keyboard(user.current_model, user.send_mode, user.search_enabled)
    )
