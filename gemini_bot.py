import io

import requests
import telebot
from dotenv import load_dotenv
from google import genai
from PIL import Image
from telebot import types
from telebot.types import BotCommand
from google.genai import types as genai_types

from constants import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    GEMINI_API_KEY,
    GREETING_MESSAGE_TEMPLATE,
    TELEGRAM_TOKEN,
    SEND_MODE_MANUAL,
    SEND_MODE_IMMEDIATE,
    MAX_FILE_SIZE_MB,
    SUPPORTED_MIME_TYPES,
)
from image_generation import generate_image_direct
from utils import markdown_to_text, split_long_message


load_dotenv()

client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)
try:
    bot.set_my_commands(
        [
            BotCommand("start", "🚀 Перезапустить бота / Начать чат"),
            BotCommand("send_mode", "✍️ Переключить режим отправки (мгновенный/ручной)"),
            BotCommand("generate", "🖼️ Сгенерировать изображение (напр. /generate кот)"),
        ]
    )
except Exception as e:
    print(f"Error setting bot commands: {e}")

user_chats = {}
user_models = {}
user_last_responses = {}
user_send_modes = {}
user_message_buffer = {}
user_files_context = {}


def get_main_keyboard(user_id):
    """Создает основную клавиатуру."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Новый чат"))
    keyboard.add(
        types.KeyboardButton("Выбрать модель"), types.KeyboardButton("/send_mode")
    )
    keyboard.add(types.KeyboardButton("Получить .MD"))

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


def download_telegram_image(file_id):
    """Загружает изображение из Telegram."""
    file_info = bot.get_file(file_id)
    file_url = (
        f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
    )
    response = requests.get(file_url)
    return io.BytesIO(response.content)


def send_text_as_file(chat_id, text, filename="response.txt"):
    """Отправляет ответ в виде файла."""
    file_obj = io.BytesIO(text.encode("utf-8"))
    bot.send_document(
        chat_id,
        file_obj,
        caption="Ваш запрошенный ответ",
        visible_file_name=filename,
    )


@bot.message_handler(commands=["start"])
def send_welcome(message):
    """Обрабатывает команду /start."""
    user_id = message.from_user.id
    user_models[user_id] = DEFAULT_MODEL
    user_chats[user_id] = client.chats.create(model=user_models[user_id])
    user_last_responses[user_id] = None
    user_send_modes[user_id] = SEND_MODE_IMMEDIATE
    user_message_buffer[user_id] = []
    user_files_context[user_id] = []
    user_last_responses[user_id] = None
    greeting_text = GREETING_MESSAGE_TEMPLATE.format(
        model_name=user_models[user_id],
        send_mode=user_send_modes[user_id],
    )
    bot.send_message(
        message.chat.id,
        greeting_text,
        reply_markup=get_main_keyboard(user_id),
    )


@bot.message_handler(func=lambda message: message.text == "Новый чат")
def new_chat(message):
    """Обрабатывает нажатие кнопки "Новый чат"."""
    user_id = message.from_user.id

    if user_id not in user_models:
        user_models[user_id] = DEFAULT_MODEL

    user_chats[user_id] = client.chats.create(model=user_models[user_id])
    user_last_responses[user_id] = None
    user_files_context[user_id] = []
    user_message_buffer[user_id] = []

    current_mode = user_send_modes.get(user_id, SEND_MODE_IMMEDIATE)

    bot.send_message(
        message.chat.id,
        f"Начат новый чат. Контекст предыдущего разговора очищен.\n\n"
        f"Текущая модель: {user_models[user_id]}\n"
        f"Режим отправки: {current_mode}",
        reply_markup=get_main_keyboard(user_id),
    )


@bot.message_handler(
    func=lambda message: message.text == "Получить .MD",
)
def get_response_as_md(message):
    """Обрабатывает нажатие кнопки "Получить .MD"."""
    user_id = message.from_user.id

    if user_last_responses.get(user_id):
        words = user_last_responses[user_id].split()
        filename = "_".join(words[:3]) + ".md" if len(words) > 0 else "response.md"
        filename = filename.replace("/", "_").replace("\\", "_").replace(":", "_")

        send_text_as_file(
            message.chat.id,
            user_last_responses[user_id],
            filename,
        )
    else:
        bot.send_message(
            message.chat.id,
            "У меня нет сохраненных ответов для отправки в виде файла.",
            reply_markup=get_main_keyboard(user_id),
        )


@bot.message_handler(commands=["send_mode"])
def handle_send_mode(message):
    """Переключает режим отправки сообщений."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    current_mode = user_send_modes.get(user_id, SEND_MODE_IMMEDIATE)

    new_mode = (
        SEND_MODE_MANUAL if current_mode == SEND_MODE_IMMEDIATE else SEND_MODE_IMMEDIATE
    )

    user_send_modes[user_id] = new_mode

    user_message_buffer[user_id] = []

    mode_message = f"Режим отправки изменен на: *{new_mode}*\n\n"
    if new_mode == SEND_MODE_MANUAL:
        mode_message += "Теперь ваши сообщения будут накапливаться. Нажмите кнопку 'Отправить всё', чтобы отправить их в Gemini."
    else:
        mode_message += (
            "Теперь каждое ваше сообщение будет сразу отправляться в Gemini."
        )

    mode_message += "\n\nБуфер сообщений очищен."

    bot.send_message(
        chat_id,
        mode_message,
        reply_markup=get_main_keyboard(user_id),
    )


@bot.message_handler(func=lambda message: message.text == "Выбрать модель")
def select_model(message):
    """Обрабатывает нажатие кнопки "Выбрать модель"."""
    bot.send_message(
        message.chat.id,
        "Выберите модель Gemini:",
        reply_markup=get_model_selection_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == "Отправить всё")
def handle_send_all(message):
    """Отправляет накопленные сообщения (текст и фото) из буфера, сохраняя разрывы между текстами."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    current_mode = user_send_modes.get(user_id, SEND_MODE_IMMEDIATE)
    if current_mode != SEND_MODE_MANUAL:
        bot.reply_to(
            message,
            f"Эта кнопка работает только в режиме '{SEND_MODE_MANUAL}'. "
            f"Ваш текущий режим: '{current_mode}'. Используйте /send_mode.",
            reply_markup=get_main_keyboard(user_id),
        )
        return

    buffered_items = user_message_buffer.get(user_id, [])

    if not buffered_items:
        bot.reply_to(
            message,
            "Буфер сообщений пуст. Нечего отправлять.",
            reply_markup=get_main_keyboard(user_id),
        )
        return

    if user_id not in user_chats:
        bot.reply_to(
            message,
            "Ошибка: сессия чата не найдена. Пожалуйста, начните новый чат.",
            reply_markup=get_main_keyboard(user_id),
        )
        user_message_buffer[user_id] = []
        return

    combined_parts = []
    current_text_block = ""

    for item in buffered_items:
        if item["type"] == "text":

            if current_text_block:
                current_text_block += "\n\n" + item["content"]
            else:

                current_text_block = item["content"]
        elif item["type"] == "photo":

            if current_text_block:
                combined_parts.append(current_text_block)
                current_text_block = ""

            if item.get("caption"):
                combined_parts.append(item["caption"])
            combined_parts.append(item["image"])
        elif item["type"] == "document":
            if current_text_block:
                combined_parts.append(current_text_block)
                current_text_block = ""
            if item.get("caption"):
                combined_parts.append(item["caption"])
            try:
                combined_parts.append(
                    genai_types.Part.from_bytes(
                        mime_type=item["mime_type"], data=item["data"]
                    )
                )

                combined_parts.append(f"(Файл: {item['filename']})")
            except Exception as file_err:
                bot.send_message(
                    chat_id,
                    f"⚠️ Не удалось добавить файл '{item['filename']}' из буфера в запрос: {file_err}",
                )

                continue

    if current_text_block:
        combined_parts.append(current_text_block)

    if not combined_parts:
        bot.reply_to(
            message,
            "Не удалось сформировать сообщение для отправки из буфера (возможно, он пуст или содержит только пустые элементы).",
            reply_markup=get_main_keyboard(user_id),
        )
        user_message_buffer[user_id] = []
        return

    bot.send_chat_action(chat_id, "typing")
    status_msg = bot.reply_to(
        message, "Отправляю накопленные сообщения и фото в Gemini..."
    )

    try:
        response = user_chats[user_id].send_message(message=combined_parts)
        raw_response_text = response.text

        user_message_buffer[user_id] = []
        user_last_responses[user_id] = raw_response_text

        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass

        plain_response_text = markdown_to_text(raw_response_text)
        message_parts = split_long_message(plain_response_text)

        for i, part in enumerate(message_parts):
            if i == 0:
                bot.send_message(chat_id, part, reply_to_message_id=message.message_id)
            else:
                bot.send_message(chat_id, part)

        if len(message_parts) > 1:
            bot.send_message(
                chat_id,
                "Ответ был разбит на несколько сообщений.",
                reply_markup=get_file_download_keyboard(user_id),
            )

    except Exception as e:
        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass
        bot.reply_to(
            message,
            f"Произошла ошибка при отправке: {e!s}\n\n"
            "Ваши сообщения и фото сохранены в буфере. Попробуйте позже или измените содержимое буфера.",
            reply_markup=get_main_keyboard(user_id),
        )

    except Exception as e:
        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass
        bot.reply_to(
            message,
            f"Произошла ошибка при отправке: {e!s}\n\n"
            "Ваши сообщения и фото сохранены в буфере. Попробуйте позже или измените содержимое буфера.",
            reply_markup=get_main_keyboard(user_id),
        )


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


@bot.callback_query_handler(func=lambda call: call.data.startswith("get_file_"))
def handle_get_file(call):
    """Обрабатывает нажатие инлайн кнопки "Получить в виде файла"."""
    user_id = int(call.data.split("_")[2])

    if user_last_responses.get(user_id):

        raw_response = user_last_responses[user_id]

        words = raw_response.split()
        filename = "_".join(words[:3]) + ".txt" if len(words) > 0 else "response.txt"
        filename = filename.replace("/", "_").replace("\\", "_").replace(":", "_")
        plain_text_response = markdown_to_text(raw_response)

        send_text_as_file(
            call.message.chat.id,
            plain_text_response,
            filename,
        )
        bot.answer_callback_query(call.id, text="Текстовый файл отправлен!")
    else:
        bot.answer_callback_query(
            call.id,
            text="У меня нет сохраненных ответов для отправки в виде файла.",
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("model_"))
def handle_model_selection(call):
    """Обрабатывает нажатия кнопок выбора модели."""
    user_id = call.from_user.id
    selected_model = call.data.replace("model_", "")

    user_models[user_id] = selected_model

    user_chats[user_id] = client.chats.create(model=user_models[user_id])
    user_last_responses[user_id] = None
    user_files_context[user_id] = []
    user_message_buffer[user_id] = []

    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"Выбрана модель: {selected_model}\n\n"
            f"Контекст предыдущего разговора очищен."
        ),
    )

    bot.send_message(
        call.message.chat.id,
        "Можете начать новый диалог.",
        reply_markup=get_main_keyboard(user_id),
    )


@bot.message_handler(content_types=["document"])
def handle_document(message):
    """Обрабатывает входящие документы поддерживаемых типов, сохраняя их в контекст."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in user_models:
        user_models[user_id] = DEFAULT_MODEL
        user_send_modes[user_id] = SEND_MODE_IMMEDIATE
        user_message_buffer[user_id] = []
        user_files_context[user_id] = []
        user_last_responses[user_id] = None
        bot.send_message(
            chat_id,
            "Похоже, мы не общались раньше. Начинаю новый чат "
            f"с моделью: {user_models[user_id]}.",
            reply_markup=get_main_keyboard(user_id),
        )
        if user_id not in user_chats:
            try:
                user_chats[user_id] = client.chats.create(model=user_models[user_id])
            except Exception as e:
                bot.reply_to(
                    message, f"Ошибка инициализации чата при первом документе: {e!s}"
                )
                return

    doc_mime_type = message.document.mime_type
    if doc_mime_type in SUPPORTED_MIME_TYPES:
        try:
            bot.send_chat_action(chat_id, "upload_document")
            file_info = bot.get_file(message.document.file_id)

            if file_info.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                bot.reply_to(
                    message,
                    f"❌ Файл '{message.document.file_name}' слишком большой "
                    f"(> {MAX_FILE_SIZE_MB} МБ). Я могу обрабатывать файлы размером до {MAX_FILE_SIZE_MB} МБ.",
                    reply_markup=get_main_keyboard(user_id),
                )
                return

            downloaded_file = bot.download_file(file_info.file_path)
            pdf_bytes = downloaded_file
            filename = message.document.file_name
            caption = message.caption or ""

            file_data = {
                "mime_type": doc_mime_type,
                "data": pdf_bytes,
                "filename": filename,
                "caption": caption,
            }

            if user_id not in user_files_context:
                user_files_context[user_id] = []
            user_files_context[user_id].append(file_data)
            context_count = len(user_files_context[user_id])

            current_mode = user_send_modes.get(user_id, SEND_MODE_IMMEDIATE)

            if current_mode == SEND_MODE_MANUAL:
                # Добавляем в буфер для ручного режима
                if user_id not in user_message_buffer:
                    user_message_buffer[user_id] = []
                user_message_buffer[user_id].append({**file_data, "type": "document"})
                buffer_count = len(user_message_buffer[user_id])
                file_type_short = doc_mime_type.split("/")[-1].upper()
                bot.reply_to(
                    message,
                    f"📄 Файл '{filename}' ({file_type_short}) добавлен в буфер ({buffer_count} шт.). "
                    + ("Подпись также добавлена.\n" if caption else "\n")
                    + f"Всего файлов в контексте: {context_count}.\n"
                    + "Нажмите 'Отправить всё', когда будете готовы.",
                    reply_markup=get_main_keyboard(user_id),
                )
            else:
                file_type_short = doc_mime_type.split("/")[-1].upper()
                bot.reply_to(
                    message,
                    f"✅ Файл '{filename}' ({file_type_short}) добавлен в контекст (всего: {context_count}). "
                    "Он будет автоматически использован при следующем текстовом запросе.",
                    reply_markup=get_main_keyboard(user_id),
                )

        except Exception as e:
            bot.reply_to(
                message,
                f"Не удалось обработать файл '{message.document.file_name}': {e!s}",
                reply_markup=get_main_keyboard(user_id),
            )
    else:
        supported_types_str = ", ".join(
            sorted(
                [
                    t.split("/")[-1].upper()
                    for t in SUPPORTED_MIME_TYPES
                    if not t.startswith("application/x")
                ]
            )
        )
        bot.reply_to(
            message,
            f"Извините, я не могу обработать этот тип файла ({doc_mime_type}). \nПоддерживаемые типы: {supported_types_str}",
            reply_markup=get_main_keyboard(user_id),
        )


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    """Обрабатывает сообщения с фотографиями в зависимости от режима."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in user_models:
        user_models[user_id] = DEFAULT_MODEL
        user_send_modes[user_id] = SEND_MODE_IMMEDIATE
        user_message_buffer[user_id] = []
        user_last_responses[user_id] = None
        bot.send_message(
            chat_id,
            "Похоже, мы не общались раньше. Начинаю новый чат "
            f"с моделью: {user_models[user_id]}.",
            reply_markup=get_main_keyboard(user_id),
        )

        if user_id not in user_chats:
            try:
                user_chats[user_id] = client.chats.create(model=user_models[user_id])
            except Exception as e:
                bot.reply_to(
                    message, f"Ошибка инициализации чата при первом фото: {e!s}"
                )
                return

    current_mode = user_send_modes.get(user_id, SEND_MODE_IMMEDIATE)

    file_id = message.photo[-1].file_id
    caption = message.caption if message.caption else ""
    if current_mode == SEND_MODE_MANUAL:
        try:
            bot.send_chat_action(chat_id, "typing")
            image_stream = download_telegram_image(file_id)
            img = Image.open(image_stream)

            if user_id not in user_message_buffer:
                user_message_buffer[user_id] = []
            user_message_buffer[user_id].append(
                {"type": "photo", "image": img, "caption": caption}
            )
            buffer_count = len(user_message_buffer[user_id])
            bot.reply_to(
                message,
                f"Фото добавлено в буфер ({buffer_count} шт.). "
                + ("Подпись также добавлена.\n" if caption else "\n")
                + "Нажмите 'Отправить всё', когда будете готовы.",
                reply_markup=get_main_keyboard(user_id),
            )
        except Exception as e:
            bot.reply_to(
                message,
                f"Не удалось добавить фото в буфер: {e!s}",
                reply_markup=get_main_keyboard(user_id),
            )
        return

    if user_id not in user_chats:
        try:

            user_chats[user_id] = client.chats.create(model=user_models[user_id])
            user_last_responses[user_id] = None
        except Exception as e:
            bot.reply_to(
                message,
                f"Не удалось инициализировать чат перед отправкой фото: {e!s}",
                reply_markup=get_main_keyboard(user_id),
            )
            return

    bot.send_chat_action(chat_id, "typing")
    try:
        image_stream = download_telegram_image(file_id)
        img = Image.open(image_stream)

        api_message_parts = []
        effective_caption = caption if caption else "Опиши это изображение."
        api_message_parts.append(effective_caption)
        api_message_parts.append(img)

        chat_session = user_chats[user_id]
        response = chat_session.send_message(message=api_message_parts)

        raw_response_text = response.text
        user_last_responses[user_id] = raw_response_text

        plain_response_text = markdown_to_text(raw_response_text)
        message_parts = split_long_message(plain_response_text)

        for i, part in enumerate(message_parts):
            if i == 0:
                bot.reply_to(message, part)
            else:
                bot.send_message(chat_id, part)

        if len(message_parts) > 1:
            bot.send_message(
                chat_id,
                "Ответ был разбит на несколько сообщений. Вы можете "
                "получить полный ответ в виде файла.",
                reply_markup=get_file_download_keyboard(user_id),
            )

    except Exception as e:
        bot.reply_to(
            message,
            f"Произошла ошибка при обработке изображения ({user_models.get(user_id, 'неизвестно')}): {e!s}\n\n"
            "Возможно, стоит попробовать новый чат.",
            reply_markup=get_main_keyboard(user_id),
        )


@bot.message_handler(commands=["generate"])
def handle_generate_command(message):
    """Обрабатывает команду /generate для создания изображений."""
    try:

        prompt = message.text.split("/generate", 1)[1].strip()

        if not prompt:
            bot.reply_to(
                message,
                "Пожалуйста, укажите запрос после команды /generate.\n"
                "Например: `/generate красивый рыжий кот`",
            )
            return

        user_id = message.from_user.id
        chat_id = message.chat.id

        bot.send_chat_action(chat_id, "upload_photo")
        bot.reply_to(message, f'Генерирую изображение по запросу: "{prompt}"...')

        image_stream = generate_image_direct(prompt)

        if image_stream:
            bot.send_photo(
                chat_id,
                image_stream,
                caption=f"Изображение по запросу: {prompt}",
                reply_to_message_id=message.message_id,
            )
        else:
            bot.reply_to(
                message,
                "Не удалось сгенерировать изображение. Попробуйте "
                "изменить запрос или проверьте настройки API.",
                reply_markup=get_main_keyboard(user_id),
            )

    except IndexError:

        bot.reply_to(
            message,
            "Пожалуйста, укажите запрос после команды /generate.\n"
            "Например: `/generate красивый рыжий кот`",
        )
    except Exception as e:
        print(f"Error during image generation command: {e}")
        bot.reply_to(
            message,
            f"Произошла ошибка при генерации изображения: {e!s}",
            reply_markup=get_main_keyboard(user_id),
        )


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Обрабатывает текстовые сообщения."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id not in user_models:
        user_models[user_id] = DEFAULT_MODEL
        user_send_modes[user_id] = SEND_MODE_IMMEDIATE
        user_message_buffer[user_id] = []
        user_last_responses[user_id] = None

        try:
            model = genai.GenerativeModel(model_name=user_models[user_id])
            user_chats[user_id] = model.start_chat(history=[])
        except Exception as e:
            bot.reply_to(message, f"Ошибка инициализации при первом сообщении: {e!s}")

    current_mode = user_send_modes.get(user_id, SEND_MODE_IMMEDIATE)

    if current_mode == SEND_MODE_MANUAL:
        if user_id not in user_message_buffer:
            user_message_buffer[user_id] = []
        user_message_buffer[user_id].append({"type": "text", "content": message.text})
        buffer_count = len(user_message_buffer[user_id])
        bot.reply_to(
            message,
            f"Сообщение добавлено в буфер ({buffer_count} шт.). Нажмите 'Отправить всё', когда будете готовы.",
        )
        return

    bot.send_chat_action(message.chat.id, "typing")

    try:

        api_message_parts = []

        files_in_context = user_files_context.get(user_id, [])
        if files_in_context:
            bot.send_message(
                chat_id,
                f"📎 Использую {len(files_in_context)} файл(а/ов) из контекста...",
            )
            for file_info in files_in_context:

                if file_info["caption"]:
                    api_message_parts.append(file_info["caption"])

                try:
                    api_message_parts.append(
                        genai_types.Part.from_bytes(
                            mime_type=file_info["mime_type"], data=file_info["data"]
                        )
                    )

                    api_message_parts.append(f"(Файл: {file_info['filename']})")
                except Exception as file_err:
                    bot.send_message(
                        chat_id,
                        f"⚠️ Не удалось добавить файл '{file_info['filename']}' в запрос: {file_err}",
                    )

        api_message_parts.append(message.text)

        if user_id not in user_chats:

            try:
                model = genai.GenerativeModel(model_name=user_models[user_id])
                user_chats[user_id] = model.start_chat(history=[])
            except Exception as e:
                bot.reply_to(
                    message, f"Ошибка инициализации чата перед отправкой: {e!s}"
                )
                return

        response = user_chats[user_id].send_message(message=api_message_parts)

        raw_response_text = response.text
        user_last_responses[user_id] = raw_response_text
        plain_response_text = markdown_to_text(raw_response_text)
        message_parts = split_long_message(plain_response_text)

        for i, part in enumerate(message_parts):
            if i == 0:

                bot.reply_to(message, part)

            else:

                bot.send_message(message.chat.id, part)

        if len(message_parts) > 1:
            bot.send_message(
                message.chat.id,
                "Ответ был разбит на несколько сообщений.",
                reply_markup=get_file_download_keyboard(user_id),
            )
    except Exception as e:
        bot.reply_to(
            message,
            f"Произошла ошибка: {e!s}\n\nВозможно стоит "
            f"попробовать другую модель или начать новый чат.",
            reply_markup=get_main_keyboard(user_id),
        )


if __name__ == "__main__":
    bot.polling(none_stop=True)
