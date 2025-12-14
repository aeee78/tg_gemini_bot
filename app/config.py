import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    PRO_CODE = os.getenv("PRO_CODE")

    # Use SQLite for dev, but ready for Postgres
    # DATABASE_URL = "postgresql+asyncpg://user:password@localhost/dbname"
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db")

    MAX_MESSAGE_LENGTH = 4000
    MAX_FILE_SIZE_MB = 20

    DEFAULT_MODEL = "gemini-2.5-flash"

    AVAILABLE_MODELS = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-image-preview",
    ]

    MODEL_ALIASES = {
        "gemini-2.5-flash": "2.5 Flash 🚀",
        "gemini-2.5-pro": "2.5 Pro💡",
        "gemini-2.5-flash-lite": "2.5 Flash Lite🐣",
        "gemini-2.5-flash-image-preview": "2.5 Flash IMG🎨 (генерация и редактирование изображений)",
    }

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

config = Config()
