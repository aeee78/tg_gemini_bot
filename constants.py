import os

from dotenv import load_dotenv


load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


MAX_MESSAGE_LENGTH = 4000

MAX_FILE_SIZE_MB = 19

DEFAULT_MODEL = "gemini-2.5-flash-preview-04-17"

AVAILABLE_MODELS = [
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-pro-preview-03-25",
    "gemini-2.0-flash",
]

GREETING_MESSAGE_TEMPLATE = (
    "Привет! Я бот на основе Gemini API.\n\n"
    "Текущая модель: {model_name}\n"
    "Режим отправки: {send_mode}\n\n"
    "Напишите мне что-нибудь или используйте кнопки для "
    "управления.\n\n"
    "Используйте /send_mode для переключения между мгновенной "
    "и ручной отправкой сообщений.\n\n"
    "Используйте /search для переключения поиска в "
    "Google.\n\n"
    "Есть поддержка файлов следующих форматов:\n"
    "pdf, rtf, txt, md, xml, csv, html, css, py, js\n\n"
    "Для генерации изображений используйте команду:\n"
    "`/generate <ваш запрос>`\n"
    "Например: `/generate orange cat`\n"
    "Лучше делать запрос на английском."
)

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

SEND_MODE_IMMEDIATE = "Мгновенный ⚡"
SEND_MODE_MANUAL = "Ручной ✍️"
