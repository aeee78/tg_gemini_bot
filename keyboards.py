from telebot import types

from constants import (
    AVAILABLE_MODELS,
    SEND_MODE_IMMEDIATE,
    SEND_MODE_MANUAL,
    MODEL_ALIASES,
    get_model_alias,
)


def get_main_keyboard(
    user_id, user_send_modes, search_enabled: bool, current_model: str
):
    """Создает основную клавиатуру с динамическим текстом кнопок."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Новый чат"))

    current_send_mode = user_send_modes.get(user_id, SEND_MODE_IMMEDIATE)
    search_status_text = "Вкл ✅" if search_enabled else "Выкл ❌"

    model_button_text = f"Модель: {get_model_alias(current_model)}"
    send_mode_button_text = f"Режим: {current_send_mode}"
    search_button_text = f"Поиск: {search_status_text}"

    keyboard.add(
        types.KeyboardButton(model_button_text),
        types.KeyboardButton(send_mode_button_text),
    )
    keyboard.add(
        types.KeyboardButton("Получить .MD"), types.KeyboardButton(search_button_text)
    )

    if current_send_mode == SEND_MODE_MANUAL:
        keyboard.add(types.KeyboardButton("Отправить всё"))

    return keyboard


def get_model_selection_keyboard():
    """Создает клавиатуру выбора модели."""
    keyboard = types.InlineKeyboardMarkup()
    for model_name in AVAILABLE_MODELS:
        alias = MODEL_ALIASES.get(model_name, model_name)
        keyboard.add(
            types.InlineKeyboardButton(
                text=alias,
                callback_data=f"model_{model_name}",
            ),
        )
    return keyboard


def get_file_download_keyboard(user_id):
    """Создает инлайн клавиатуру для скачивания файла."""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            text="Получить в виде файла",
            callback_data=f"get_file_{user_id}",
        ),
    )
    return keyboard
