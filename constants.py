import os

from dotenv import load_dotenv
from telebot.types import BotCommand


load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


MAX_MESSAGE_LENGTH = 4000

MAX_FILE_SIZE_MB = 19

DEFAULT_MODEL = "gemini-2.5-flash-preview-04-17"

AVAILABLE_MODELS = [
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-pro-exp-03-25",
    "gemini-2.0-flash",
]


MODEL_ALIASES = {
    "gemini-2.5-flash-preview-04-17": "2.5 Flash 🚀",
    "gemini-2.5-pro-exp-03-25": "2.5 Pro💡",
    "gemini-2.0-flash": "2.0 Flash",
}


def get_model_alias(full_name, default="Неизвестно"):
    """Возвращает короткий псевдоним для полного имени модели."""
    return MODEL_ALIASES.get(full_name, default)


COMMAND_LIST = [
    BotCommand("start", "🚀 Перезапустить бота / Начать чат"),
    BotCommand("generate", "🖼️ Сгенерировать изображение (напр. /generate кот)"),
]


GREETING_MESSAGE_TEMPLATE = """
👋 Привет! Я ваш персональный помощник на базе Google Gemini.

Я могу общаться с вами на разные темы, генерировать изображения и даже использовать поиск Google для более точных ответов!

Текущие настройки:
🧠 Модель: *{model_name}*
✍️ Режим отправки: *{send_mode}*
🔎 Поиск Google: *{search_status}*

Что я умею:
💬 *Поддерживать диалог:* Я запоминаю контекст нашего разговора. Нажмите "Новый чат", чтобы начать с чистого листа.
🖼️ *Генерировать изображения:* Используйте команду `/generate <ваш запрос>` (например, `/generate рыжий кот на крыше`).
📄 *Обрабатывать фото и файлы:* Отправьте мне изображение, чтобы я его описал, или документ (PDF, TXT и др.), чтобы я учел его содержимое.
⚙️ *Выбирать модель:* Нажмите "Выбрать модель", чтобы переключиться между разными версиями Gemini.
✍️ *Режимы отправки:*
    • *{send_mode_immediate}*: Отправляю ответ сразу после вашего сообщения/фото.
    • *{send_mode_manual}*: Накапливаю ваши сообщения/фото в буфер. Нажмите "Отправить всё", чтобы отправить их мне разом.
🔎 *Искать в Google:* Я могу использовать поиск Google для получения актуальной информации.
💾 *Получать ответы файлом:* Если мой ответ слишком длинный, он будет разделен на несколько сообщений. Вы сможете скачать полный текст кнопкой "Получить .MD 📄".

Используйте кнопки ниже или просто напишите мне! 👇
"""

SEND_MODE_IMMEDIATE = "Мгновенный ⚡"
SEND_MODE_MANUAL = "Ручной ✍️"

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/x-javascript",
    "text/javascript",
    "application/x-python",
    "text/x-python",
    "text/plain",
    "text/html",
    "text/css",
    "text/markdown",
    "text/csv",
    "text/xml",
    "application/xml",
    "text/rtf",
    "application/rtf",
}
