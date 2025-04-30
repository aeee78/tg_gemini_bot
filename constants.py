import os

from dotenv import load_dotenv
from telebot.types import BotCommand
from quick_tools_config import QUICK_TOOLS_CONFIG

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
    BotCommand("/start", "🚀 Перезапустить бота / Начать чат"),
    BotCommand("/generate", "🖼️ Сгенерировать изображение (напр. /generate кот)"),
]


for command_name, config in QUICK_TOOLS_CONFIG.items():
    COMMAND_LIST.append(BotCommand(f"/{command_name}", config["description"]))


GREETING_MESSAGE_TEMPLATE = """
👋 Привет! Я ваш персональный помощник на базе Google Gemini.

Я помню наш разговор (контекст), могу работать с файлами, генерировать изображения и использовать поиск Google.

Текущие настройки:
🧠 Модель: *{model_name}*
✍️ Режим отправки: *{send_mode}*
🔎 Поиск Google: *{search_status}*

Что я умею:
💬 *Помнить контекст:* Я учитываю предыдущие сообщения в диалоге. Нажмите "Новый чат", чтобы начать с чистого листа.
📄 *Работать с файлами:* Отправьте мне фото (я его опишу или учту) или документ (PDF, TXT, код и др. Файлы добавляются в контекст текущего чата и будут использованы при следующем текстовом запросе (в Мгновенном режиме) или при нажатии "Отправить всё" (в Ручном режиме).
🖼️ *Генерировать изображения:* `/generate <ваш запрос>` (например, `/generate orange cat`). Это отдельная функция, не влияющая на чат, лучше делать запрос на английском.
⚙️ *Выбирать модель:* Кнопка "Модель: ..." позволяет переключиться между версиями Gemini (смена модели начинает новый чат).
✍️ *Режимы отправки:*
    • *{send_mode_immediate}*: Отправляю ваш текст/фото/файл *сразу* после получения. Файлы из контекста добавляются к следующему текстовому запросу.
    • *{send_mode_manual}*: Накапливаю ваши сообщения/фото/файлы в буфер. Удобно, чтобы собрать *один большой запрос* из нескольких частей или отправить очень длинный текст. Нажмите "Отправить всё", чтобы обработать буфер.
🔎 *Искать в Google:* Кнопка "Поиск: ..." включает/выключает поиск для более актуальных ответов и ссылок на источники.
💾 *Скачивать ответы:*
    • Кнопка "Скачать .md📄": Получить *последний* ответ бота в виде Markdown-файла (с форматированием).
    • Если ответ был слишком длинным и разбит на части, появится кнопка "Скачать в формате .txt" под сообщением для получения полного текста без форматирования.

💡 *Подсказка:* Используйте /help для полного списка команд и пояснений.

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
