from dotenv import load_dotenv
import os

load_dotenv()


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MAX_MESSAGE_LENGTH = 4000

AVAILABLE_MODELS = [
    "gemini-2.0-flash-thinking-exp-01-21",
    "gemini-2.5-pro-exp-03-25",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp-image-generation",
]

IMAGE_COMMAND_PREFIXES = [
    "нарисуй",
    "сгенерируй изображение",
    "создай изображение",
    "draw",
    "generate image",
]

GREETING_MESSAGE_TEMPLATE = (
    "Привет! Я бот на основе Gemini API.\n\n"
    "Текущая модель: {model_name}\n\n"
    "Напишите мне что-нибудь или используйте кнопки для "
    "управления.\n\n"
    "Для генерации изображений используйте модель "
    "'gemini-2.0-flash-exp-image-generation' "
    "и начните сообщение со слов 'нарисуй' или "
    "'сгенерируй изображение'.\n\n"
)
