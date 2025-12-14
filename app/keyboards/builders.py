from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from app.config import config

def get_main_keyboard(current_model: str, send_mode: str, search_enabled: bool) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    search_status = "Вкл ✅" if search_enabled else "Выкл ❌"
    model_alias = config.MODEL_ALIASES.get(current_model, "Неизвестно")

    builder.row(KeyboardButton(text="Новый чат"))
    builder.row(
        KeyboardButton(text=f"Модель: {model_alias}"),
        KeyboardButton(text=f"Режим: {send_mode}")
    )
    builder.row(
        KeyboardButton(text="Получить .MD 📄"),
        KeyboardButton(text=f"Поиск: {search_status}")
    )

    if send_mode == config.SEND_MODE_MANUAL:
        builder.row(KeyboardButton(text="Отправить всё"))

    return builder.as_markup(resize_keyboard=True)

def get_model_selection_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for model_name in config.AVAILABLE_MODELS:
        alias = config.MODEL_ALIASES.get(model_name, model_name)
        builder.row(InlineKeyboardButton(text=alias, callback_data=f"model_{model_name}"))
    return builder.as_markup()

def get_file_download_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Скачать в формате .txt", callback_data=f"get_file_{user_id}"))
    builder.row(InlineKeyboardButton(text="Скачать в формате .md", callback_data=f"get_md_{user_id}"))
    return builder.as_markup()
