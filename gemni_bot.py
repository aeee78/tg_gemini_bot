import base64
import io
import os

import google.generativeai as genai
import requests
import telebot
from dotenv import load_dotenv
from PIL import Image
from telebot import types

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MAX_MESSAGE_LENGTH = 4000

AVAILABLE_MODELS = [
    "gemini-2.0-flash-thinking-exp-01-21",
    "gemini-2.5-pro-exp-03-25",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-exp-image-generation",
]

genai.configure(api_key=GEMINI_API_KEY)

bot = telebot.TeleBot(TELEGRAM_TOKEN)

user_chats = {}
user_models = {}
user_last_responses = {}

IMAGE_COMMAND_PREFIXES = [
    "нарисуй",
    "сгенерируй изображение",
    "создай изображение",
    "draw",
    "generate image",
]


def get_main_keyboard():
    """Создает основную клавиатуру    ."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Новый чат"))
    keyboard.add(types.KeyboardButton("Выбрать модель"))
    keyboard.add(types.KeyboardButton("Получить ответ как файл"))
    return keyboard


def get_model_selection_keyboard():
    """Создает клавиатуру выбора модели."""
    keyboard = types.InlineKeyboardMarkup()
    for model_name in AVAILABLE_MODELS:
        keyboard.add(
            types.InlineKeyboardButton(
                text=model_name, callback_data=f"model_{model_name}",
            ),
        )
    return keyboard


def is_image_generation_request(text):
    """Проверяет, является ли запрос запросом на генерацию изображения."""
    text_lower = text.lower()
    return any(
        text_lower.startswith(prefix) for prefix in IMAGE_COMMAND_PREFIXES
    )


def download_telegram_image(file_id):
    """Загружает изображение из Telegram."""
    file_info = bot.get_file(file_id)
    file_url = (
        f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/"
        f"{file_info.file_path}"
    )
    response = requests.get(file_url)
    return io.BytesIO(response.content)


def split_long_message(text, max_length=MAX_MESSAGE_LENGTH):
    """Разбивает длинный текст на части."""
    if len(text) <= max_length:
        return [text]

    parts = []
    current_part = ""

    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        if len(paragraph) > max_length:
            sentences = paragraph.split(". ")
            for sentence in sentences:
                if len(current_part + sentence + ". ") <= max_length:
                    current_part += sentence + ". "
                else:
                    if current_part:
                        parts.append(current_part)
                    current_part = sentence + ". "
        elif len(current_part + paragraph + "\n\n") <= max_length:
            current_part += paragraph + "\n\n"
        else:
            if current_part:
                parts.append(current_part)
            current_part = paragraph + "\n\n"

    if current_part:
        parts.append(current_part)

    return parts


def send_text_as_file(chat_id, text, filename="response.md"):
    """Отправляет ответ в виде файла."""
    file_obj = io.BytesIO(text.encode("utf-8"))
    bot.send_document(
        chat_id,
        file_obj,
        caption="Ваш запрошенный ответ",
        visible_file_name=filename,
    )


def generate_image_direct(prompt):
    """Генерирует изображение через API."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash-exp-image-generation:generateContent"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    data = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generation_config": {
            "temperature": 1.0,
            "topP": 0.95,
            "topK": 64,
            "response_modalities": ["Text", "Image"],
        },
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        response_json = response.json()
        candidates = response_json.get("candidates", [])
        if candidates and len(candidates) > 0:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    image_data = part["inlineData"].get("data")
                    if image_data:
                        image_bytes = base64.b64decode(image_data)
                        return io.BytesIO(image_bytes)

    error_info = f"Status code: {response.status_code}"
    try:
        error_info += f", Response: {response.json()}"
    except Exception:
        error_info += f", Response: {response.text}"

    print(f"Debug - Image generation error: {error_info}")
    return None


@bot.message_handler(commands=["start"])
def send_welcome(message):
    """Обрабатывает команду /start."""
    user_id = message.from_user.id
    user_models[user_id] = "gemini-2.0-flash-thinking-exp-01-21"
    model = genai.GenerativeModel(model_name=user_models[user_id])
    user_chats[user_id] = model.start_chat(history=[])

    bot.send_message(
        message.chat.id,
        f"Привет! Я бот на основе Gemini API.\n\n"
        f"Текущая модель: {user_models[user_id]}\n\n"
        f"Напишите мне что-нибудь или используйте кнопки для "
        f"управления.\n\n"
        f"Для генерации изображений используйте модель "
        f"'gemini-2.0-flash-exp-image-generation' "
        f"и начните сообщение со слов 'нарисуй' или "
        f"'сгенерируй изображение'.\n\n"
        f"Вы также можете отправить мне изображение, и я опишу, "
        f"что на нём.\n\n"
        f"Если ответ слишком длинный, вы можете получить его в "
        f"виде текстового файла.",
        reply_markup=get_main_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == "Новый чат")
def new_chat(message):
    """Обрабатывает нажатие кнопки "Новый чат"."""
    user_id = message.from_user.id

    if user_id not in user_models:
        user_models[user_id] = "gemini-2.0-flash-thinking-exp-01-21"

    model = genai.GenerativeModel(model_name=user_models[user_id])
    user_chats[user_id] = model.start_chat(history=[])

    user_last_responses[user_id] = None

    bot.send_message(
        message.chat.id,
        f"Начат новый чат. Контекст предыдущего разговора очищен.\n\n"
        f"Текущая модель: {user_models[user_id]}",
        reply_markup=get_main_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == "Выбрать модель")
def select_model(message):
    """Обрабатывает нажатие кнопки "Выбрать модель"."""
    bot.send_message(
        message.chat.id,
        "Выберите модель Gemini:",
        reply_markup=get_model_selection_keyboard(),
    )


@bot.message_handler(
    func=lambda message: message.text == "Получить ответ как файл",
)
def get_response_as_file(message):
    """Обрабатывает нажатие кнопки "Получить ответ как файл"."""
    user_id = message.from_user.id

    if user_last_responses.get(user_id):
        words = user_last_responses[user_id].split()
        filename = (
            "_".join(words[:3]) + ".md" if len(words) > 0 else "response.md"
        )
        filename = (
            filename.replace("/", "_").replace("\\", "_").replace(":", "_")
        )

        send_text_as_file(
            message.chat.id, user_last_responses[user_id], filename,
        )
    else:
        bot.send_message(
            message.chat.id,
            "У меня нет сохраненных ответов для отправки в виде файла.",
            reply_markup=get_main_keyboard(),
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("model_"))
def handle_model_selection(call):
    """Обрабатывает нажатия кнопок выбора модели."""
    user_id = call.from_user.id
    selected_model = call.data.replace("model_", "")

    user_models[user_id] = selected_model

    model = genai.GenerativeModel(model_name=selected_model)
    user_chats[user_id] = model.start_chat(history=[])

    user_last_responses[user_id] = None

    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"Выбрана модель: {selected_model}\n\n"
            f"Контекст предыдущего разговора очищен."
        ),
    )

    if selected_model == "gemini-2.0-flash-exp-image-generation":
        bot.send_message(
            call.message.chat.id,
            "Вы выбрали модель с поддержкой генерации изображений.\n\n"
            "Для создания изображения начните сообщение со слов "
            "'нарисуй' или 'сгенерируй изображение'.",
            reply_markup=get_main_keyboard(),
        )
    else:
        bot.send_message(
            call.message.chat.id,
            "Можете начать новый диалог.",
            reply_markup=get_main_keyboard(),
        )


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    """Обрабатывает сообщения с фотографиями."""
    user_id = message.from_user.id

    if user_id not in user_models:
        user_models[user_id] = "gemini-2.0-pro-exp-02-05"

    file_id = message.photo[-1].file_id

    bot.send_chat_action(message.chat.id, "typing")

    try:
        image_stream = download_telegram_image(file_id)

        image_model = genai.GenerativeModel(
            model_name="gemini-2.0-pro-exp-02-05",
        )

        img = Image.open(image_stream)

        caption = (
            message.caption if message.caption else "What's in this image?"
        )

        response = image_model.generate_content([caption, img])
        response_text = response.text

        user_last_responses[user_id] = response_text

        message_parts = split_long_message(response_text)

        for i, part in enumerate(message_parts):
            if i == 0:
                bot.reply_to(message, part)
            else:
                bot.send_message(message.chat.id, part)

        if len(message_parts) > 1:
            bot.send_message(
                message.chat.id,
                "Ответ был разбит на несколько сообщений. Вы можете "
                "получить полный ответ в виде файла.",
                reply_markup=get_main_keyboard(),
            )

    except Exception as e:
        bot.reply_to(
            message,
            f"Произошла ошибка при обработке изображения: {e!s}\n\n"
            f"Убедитесь, что выбрана модель с поддержкой "
            f"мультимодальности.",
            reply_markup=get_main_keyboard(),
        )


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Обрабатывает текстовые сообщения."""
    user_id = message.from_user.id

    if user_id not in user_models:
        user_models[user_id] = "gemini-2.0-flash-thinking-exp-01-21"

    if user_id not in user_chats:
        model = genai.GenerativeModel(model_name=user_models[user_id])
        user_chats[user_id] = model.start_chat(history=[])

    bot.send_chat_action(message.chat.id, "typing")

    try:
        current_model = user_models[user_id]
        if (
            current_model == "gemini-2.0-flash-exp-image-generation"
            and is_image_generation_request(message.text)
        ):
            bot.send_chat_action(message.chat.id, "upload_photo")

            prompt = message.text
            image_stream = generate_image_direct(prompt)

            if image_stream:
                bot.send_photo(
                    message.chat.id,
                    image_stream,
                    caption=f"Изображение по запросу: {prompt}",
                )
            else:
                bot.reply_to(
                    message,
                    "Не удалось сгенерировать изображение. Попробуйте "
                    "изменить запрос или проверьте API ключ.",
                    reply_markup=get_main_keyboard(),
                )
        else:
            response = user_chats[user_id].send_message(message.text)
            response_text = response.text

            user_last_responses[user_id] = response_text

            message_parts = split_long_message(response_text)

            for i, part in enumerate(message_parts):
                if i == 0:
                    bot.reply_to(message, part)
                else:
                    bot.send_message(message.chat.id, part)

            if len(message_parts) > 1:
                bot.send_message(
                    message.chat.id,
                    "Ответ был разбит на несколько сообщений. Вы можете "
                    "получить полный ответ в виде файла.",
                    reply_markup=get_main_keyboard(),
                )
    except Exception as e:
        bot.reply_to(
            message,
            f"Произошла ошибка: {e!s}\n\nВозможно стоит "
            f"попробовать другую модель или начать новый чат.",
            reply_markup=get_main_keyboard(),
        )


if __name__ == "__main__":
    bot.polling(none_stop=True)
