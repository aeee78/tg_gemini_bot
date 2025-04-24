from telebot import types

from constants import AVAILABLE_MODELS, SEND_MODE_IMMEDIATE, SEND_MODE_MANUAL


def get_main_keyboard(user_id, user_send_modes):
    """Создает основную клавиатуру."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Новый чат"))
    keyboard.add(
        types.KeyboardButton("Выбрать модель"), types.KeyboardButton("/send_mode")
    )
    keyboard.add(types.KeyboardButton("Получить .MD"), types.KeyboardButton("/search")))
    

    if user_send_modes.get(user_id, SEND_MODE_IMMEDIATE) == SEND_MODE_MANUAL:
        keyboard.add(types.KeyboardButton("Отправить всё"))

    return keyboard


def get_model_selection_keyboard():
    """Создает клавиатуру выбора модели."""
    keyboard = types.InlineKeyboardMarkup()
    for model_name in AVAILABLE_MODELS:
        keyboard.add(
            types.InlineKeyboardButton(
                text=model_name,
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
