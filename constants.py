import os

from dotenv import load_dotenv
from telebot.types import BotCommand
from quick_tools_config import QUICK_TOOLS_CONFIG

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PRO_CODE = os.getenv("PRO_CODE")


MAX_MESSAGE_LENGTH = 4000

MAX_FILE_SIZE_MB = 20

DEFAULT_MODEL = "gemini-3-flash-preview"

AVAILABLE_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-image",
]


MODEL_ALIASES = {
    "gemini-3-flash-preview": "3 Flash 🚀",
    "gemini-3.1-pro-preview": "3.1 Pro💡",
    "gemini-2.5-flash-lite": "2.5 Flash Lite🐣",
    "gemini-2.5-flash-image": "2.5 Flash IMG🎨 (генерация и редактирование изображений)",
}


def get_model_alias(full_name, default="Неизвестно"):
    """Возвращает короткий псевдоним для полного имени модели."""
    return MODEL_ALIASES.get(full_name, default)


def is_image_generation_model(model_name):
    """Проверяет, поддерживает ли модель генерацию изображений."""
    return model_name == "gemini-2.5-flash-image"


COMMAND_LIST = [
    BotCommand("/start", "🚀 Перезапустить бота / Начать чат"),
    BotCommand("/help", "ℹ️ Справка по возможностям бота"),
]


for command_name, config in QUICK_TOOLS_CONFIG.items():
    COMMAND_LIST.append(BotCommand(f"/{command_name}", config["description"]))


GREETING_MESSAGE_TEMPLATE = """
👋 *Привет! Я — бот на базе Google Gemini.*

Я помню контекст диалога, умею работать с документами, искать информацию в Google и рисовать.

📊 *Текущие настройки:*
🧠 Модель: *{model_name}*
✍️ Режим: *{send_mode}*
🔎 Поиск Google: *{search_status}*

💡 *Как пользоваться:*
Просто пишите мне или используйте кнопки меню.
Нажмите /help, чтобы узнать подробности о режимах и командах. 👇
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


HELP_TEXT_TEMPLATE = (
    "ℹ️ *Справка и возможности*\n\n"
    "🤖 *Основы чата:*\n"
    "• Я помню контекст переписки. Просто общайтесь со мной как с человеком.\n"
    "• *Новый чат:* Нажмите кнопку, чтобы стереть память и начать с чистого листа (смена модели тоже начинает новый чат).\n"
    "• *Поиск Google:* Включает доступ к интернету для актуальных ответов.\n\n"
    "🎨 *Генерация изображений:*\n"
    "Переключитесь на модель *2.5 Flash IMG🎨*.\n"
    "• *Текст → Картинка:* «Нарисуй киберпанк-город».\n"
    "• *Фото → Изменение:* Пришлите фото с подписью «Сделай черно-белым» или «Добавь очки».\n\n"
    "📄 *Работа с файлами:*\n"
    f"Присылайте PDF, TXT, CSV, код или картинки (до {MAX_FILE_SIZE_MB} МБ).\n"
    "• Я «прочитаю» их и смогу отвечать на вопросы по содержимому.\n"
    "• Файлы хранятся в контексте до нажатия «Новый чат».\n\n"
    "⚙️ *Режимы отправки (кнопка 'Режим'):*\n"
    f"1. *{SEND_MODE_IMMEDIATE}*: Я отвечаю сразу на каждое сообщение/файл. Идеально для диалога.\n"
    f"2. *{SEND_MODE_MANUAL}*: Сообщения копятся в буфер. Нажмите *«Отправить всё»*, чтобы послать их разом. Идеально для длинных промптов или анализа пачки из 5 файлов сразу.\n\n"
    "💾 *Полезные мелочи:*\n"
    "• *Скачать .md:* Кнопка меню. Скачивает последний ответ файлом (удобно для статей/кода).\n"
    "• *Быстрые инструменты:* Команды вроде /summary или /code выполняют действие без сохранения в памяти бота."
)
