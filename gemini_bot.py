import io
import json
import base64

import requests
import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from PIL import Image

from constants import (
    COMMAND_LIST,
    DEFAULT_MODEL,
    GEMINI_API_KEY,
    PRO_CODE,
    GREETING_MESSAGE_TEMPLATE,
    MAX_FILE_SIZE_MB,
    QUICK_TOOLS_CONFIG,
    SEND_MODE_IMMEDIATE,
    SEND_MODE_MANUAL,
    SUPPORTED_MIME_TYPES,
    TELEGRAM_TOKEN,
    HELP_TEXT_TEMPLATE,
    get_model_alias,
    is_image_generation_model,
)

from keyboards import (
    get_file_download_keyboard,
    get_main_keyboard,
    get_model_selection_keyboard,
)
from functools import wraps

from utils import markdown_to_text, split_long_message, BytesEncoder

from database import db, crud
from database.db import SessionLocal

load_dotenv()

client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

bot.set_my_commands(COMMAND_LIST)

# Global stores
user_chats = {}  # Cache for active chat sessions
user_last_responses = {}

WHITELIST_FILE = "whitelist.txt"
whitelisted_users = set()

# --- Helper Functions for Persistence ---


def deserialize_history(history_json):
    """Deserializes JSON history into list of types.Content."""
    if not history_json:
        return []
    try:
        data = json.loads(history_json)
        history = []
        for item in data:
            parts = []
            for part_data in item.get("parts", []):
                if "inline_data" in part_data and part_data["inline_data"]:
                    blob_data = part_data["inline_data"]
                    if "data" in blob_data and isinstance(
                        blob_data["data"], str
                    ):
                        try:
                            blob_data["data"] = base64.b64decode(
                                blob_data["data"]
                            )
                        except Exception:
                            # Already bytes or invalid base64, leaving as is
                            pass
                parts.append(genai_types.Part(**part_data))
            history.append(
                genai_types.Content(role=item.get("role"), parts=parts)
            )
        return history
    except Exception as e:
        print(f"Error deserializing history: {e}")
        return []


def get_active_chat(user_id, model_name):
    """Gets active chat from cache or loads from DB."""
    if user_id in user_chats:
        return user_chats[user_id]

    with SessionLocal() as session:
        chat_session = crud.get_chat_session(session, user_id)
        history = []
        if chat_session and chat_session.history_json:
            history = deserialize_history(chat_session.history_json)

    try:
        new_chat = client.chats.create(model=model_name, history=history)
        user_chats[user_id] = new_chat
        return new_chat
    except Exception as e:
        print(f"Error creating chat with history: {e}. Starting fresh.")
        new_chat = client.chats.create(model=model_name)
        user_chats[user_id] = new_chat
        return new_chat


def save_active_chat(user_id):
    """Saves current chat history to DB."""
    if user_id in user_chats:
        chat = user_chats[user_id]
        try:
            history_data = []
            for content in chat._curated_history:
                if hasattr(content, "model_dump"):
                    history_data.append(content.model_dump())
                else:
                    pass

            history_json = json.dumps(history_data, cls=BytesEncoder)

            with SessionLocal() as session:
                crud.save_chat_session(session, user_id, history_json)
        except Exception as e:
            print(f"Error saving chat history: {e}")


def get_file_context_list(user_id):
    with SessionLocal() as session:
        files = crud.get_file_contexts(session, user_id)
        return [
            {
                "mime_type": f.mime_type,
                "data": f.data,
                "filename": f.filename,
                "caption": f.caption,
            }
            for f in files
        ]


def add_file_context_entry(user_id, file_data):
    with SessionLocal() as session:
        crud.add_file_context(
            session,
            user_id,
            filename=file_data["filename"],
            mime_type=file_data["mime_type"],
            data=file_data["data"],
            caption=file_data.get("caption"),
        )


def get_message_buffer_list(user_id):
    with SessionLocal() as session:
        items = crud.get_buffer(session, user_id)
        result = []
        for item in items:
            entry = {"type": item.item_type}
            if item.item_type == "text":
                entry["content"] = item.content or ""
            elif item.item_type == "photo":
                entry["caption"] = item.content or ""
                if item.blob_data:
                    entry["image"] = Image.open(io.BytesIO(item.blob_data))
            elif item.item_type == "document":
                entry["mime_type"] = item.mime_type
                entry["data"] = item.blob_data
                entry["filename"] = item.filename
                entry["caption"] = item.content
            result.append(entry)
        return result


def add_to_message_buffer(user_id, entry):
    with SessionLocal() as session:
        if entry["type"] == "text":
            crud.add_to_buffer(
                session, user_id, "text", content=entry["content"]
            )
        elif entry["type"] == "photo":
            # Convert PIL image to bytes
            img_byte_arr = io.BytesIO()
            entry["image"].save(
                img_byte_arr, format=entry["image"].format or "PNG"
            )
            img_bytes = img_byte_arr.getvalue()
            crud.add_to_buffer(
                session,
                user_id,
                "photo",
                content=entry.get("caption"),
                blob_data=img_bytes,
            )
        elif entry["type"] == "document":
            crud.add_to_buffer(
                session,
                user_id,
                "document",
                content=entry.get("caption"),
                blob_data=entry["data"],
                filename=entry["filename"],
                mime_type=entry["mime_type"],
            )


def clear_user_context_db(user_id):
    with SessionLocal() as session:
        crud.clear_file_contexts(session, user_id)
        crud.clear_buffer(session, user_id)


def load_whitelist():
    """Загружает белый список пользователей из файла"""
    try:
        with open(WHITELIST_FILE, "r") as f:
            for line in f:
                user_id = line.strip()
                if user_id:
                    whitelisted_users.add(int(user_id))
        print(f"Loaded {len(whitelisted_users)} users into whitelist.")
    except FileNotFoundError:
        print(
            f"Whitelist file '{WHITELIST_FILE}' not found. Starting with empty whitelist."
        )
    except Exception as e:
        print(f"Error loading whitelist: {e}")


def add_to_whitelist(user_id):
    """Добавляет пользователя в белый список."""
    if user_id not in whitelisted_users:
        try:
            with open(WHITELIST_FILE, "a") as f:
                f.write(f"{user_id}\n")
            whitelisted_users.add(user_id)
            print(f"Added user {user_id} to whitelist.")
        except Exception as e:
            print(f"Error adding user {user_id} to whitelist: {e}")


def is_whitelisted(user_id):
    """Checks if a user ID is in the whitelist."""

    return user_id in whitelisted_users


def ensure_user_started(func):
    """Декоратор: проверяет, начал ли пользователь диалог командой /start (есть ли в БД)."""

    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if isinstance(message, telebot.types.CallbackQuery):
            user_id = message.from_user.id
            chat_id = message.message.chat.id
            is_callback = True
        elif isinstance(message, telebot.types.Message):
            user_id = message.from_user.id
            chat_id = message.chat.id
            is_callback = False
        else:
            print(
                f"Предупреждение: ensure_user_started получил неожиданный тип: {type(message)}"
            )
            return func(message, *args, **kwargs)

        with SessionLocal() as session:
            user = crud.get_user(session, user_id)
            if not user:
                try:
                    if is_callback:
                        bot.answer_callback_query(message.id)
                    bot.send_message(
                        chat_id,
                        "Пожалуйста, введите /start для начала работы.",
                        reply_markup=telebot.types.ReplyKeyboardRemove(),
                    )
                except Exception as e:
                    print(
                        f"Ошибка при отправке сообщения 'введите /start': {e}"
                    )
                return None
        return func(message, *args, **kwargs)

    return wrapper


def download_telegram_image(file_id):
    """Загружает изображение из Telegram."""
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
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


def send_gemini_response_with_images(
    chat_id, response, reply_to_message_id=None
):
    """Отправляет ответ Gemini, обрабатывая как текст, так и изображения."""
    text_parts = []

    if hasattr(response, "candidates") and response.candidates:
        for candidate in response.candidates:
            if hasattr(candidate, "content") and candidate.content:
                if (
                    hasattr(candidate.content, "parts")
                    and candidate.content.parts
                ):
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)
                        elif hasattr(part, "inline_data"):
                            try:
                                image_data = part.inline_data.data
                                mime_type = part.inline_data.mime_type

                                image_bytes = io.BytesIO(image_data)

                                if mime_type.startswith("image/"):
                                    bot.send_photo(
                                        chat_id,
                                        image_bytes,
                                        reply_to_message_id=reply_to_message_id,
                                    )
                                else:
                                    bot.send_document(
                                        chat_id,
                                        image_bytes,
                                        visible_file_name=f"generated_content.{mime_type.split('/')[-1]}",
                                        reply_to_message_id=reply_to_message_id,
                                    )
                            except Exception as e:
                                print(f"Ошибка отправки изображения: {e}")
                                text_parts.append(
                                    f"[Ошибка отправки изображения: {e}]"
                                )

    if not text_parts and hasattr(response, "text") and response.text:
        text_parts.append(response.text)

    if text_parts:
        combined_text = "\n".join(text_parts)
        plain_text = markdown_to_text(combined_text)
        message_parts = split_long_message(plain_text)

        for i, part in enumerate(message_parts):
            bot.send_message(
                chat_id,
                part,
                reply_to_message_id=reply_to_message_id if i == 0 else None,
            )

        return combined_text

    return ""


@bot.message_handler(commands=["help"])
def handle_help_command(message):
    """Выводит подробную справку по функциям бота."""
    help_text = HELP_TEXT_TEMPLATE.format(
        MAX_FILE_SIZE_MB=MAX_FILE_SIZE_MB,
        SEND_MODE_IMMEDIATE=SEND_MODE_IMMEDIATE,
        SEND_MODE_MANUAL=SEND_MODE_MANUAL,
    )

    for command_info in COMMAND_LIST:
        if command_info.command not in ["/start"]:
            example = ""
            if command_info.command == "/translate":
                example = " (напр. `/translate привет мир`)"
            elif command_info.command == "/prompt":
                example = " (напр. `/prompt напиши стих`)"
            help_text += f"- *{command_info.command}*: {command_info.description}{example}\n"
    help_text += "- *Пример:* `/translate Hello world`\n"

    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")


@bot.message_handler(commands=["unlock_pro"])
@ensure_user_started
def handle_unlock_pro(message):
    """Обрабатывает команду /unlock_pro."""
    user_id = message.from_user.id
    command_parts = message.text.split(" ", 1)

    if len(command_parts) == 2 and command_parts[1].strip() == str(PRO_CODE):
        add_to_whitelist(user_id)
        bot.reply_to(message, "✅ Доступ к про модели разблокирован!")
    else:
        bot.reply_to(message, "❌ Неверный код. Используйте другой")


@bot.message_handler(commands=["start"])
def send_welcome(message):
    """Обрабатывает команду /start."""
    user_id = message.from_user.id

    with SessionLocal() as session:
        # Create user with defaults if not exists
        user = crud.get_or_create_user(session, user_id)
        current_model = user.current_model
        send_mode = user.send_mode
        search_enabled = user.search_enabled

        # Clear buffers/files on start
        crud.clear_file_contexts(session, user_id)
        crud.clear_buffer(session, user_id)

    # Initialize chat session
    get_active_chat(user_id, current_model)

    user_last_responses[user_id] = None

    search_status_text = "Вкл ✅" if search_enabled else "Выкл ❌"

    greeting_text = GREETING_MESSAGE_TEMPLATE.format(
        model_name=get_model_alias(current_model),
        send_mode=send_mode,
        search_status=search_status_text,
        send_mode_immediate=SEND_MODE_IMMEDIATE,
        send_mode_manual=SEND_MODE_MANUAL,
    )

    bot.send_message(
        message.chat.id,
        greeting_text,
        reply_markup=get_main_keyboard(
            send_mode, search_enabled, current_model
        ),
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda message: message.text == "Новый чат")
@ensure_user_started
def new_chat(message):
    """Обрабатывает нажатие кнопки "Новый чат"."""
    user_id = message.from_user.id

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        current_model = user.current_model
        send_mode = user.send_mode
        search_enabled = user.search_enabled

        # Clear history in DB
        crud.clear_chat_session(session, user_id)
        # Clear contexts
        crud.clear_file_contexts(session, user_id)
        crud.clear_buffer(session, user_id)

    # Clear memory cache
    if user_id in user_chats:
        del user_chats[user_id]

    # Start new
    get_active_chat(user_id, current_model)

    user_last_responses[user_id] = None

    search_status = "Вкл ✅" if search_enabled else "Выкл ❌"

    bot.send_message(
        message.chat.id,
        f"Начат новый чат. Контекст предыдущего разговора очищен.\n\n"
        f"Текущая модель: {get_model_alias(current_model)}\n"
        f"Режим отправки: {send_mode}\n"
        f"Поиск Google: {search_status}",
        reply_markup=get_main_keyboard(
            send_mode, search_enabled, current_model
        ),
    )


@bot.message_handler(
    func=lambda message: message.text.startswith("Получить .")
)
@ensure_user_started
def get_response_as_md(message):
    """Обрабатывает нажатие кнопки "Получить .md 📄"."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_last_responses.get(user_id):
        raw_response = user_last_responses[user_id]

        words = raw_response.split()
        filename_base = "_".join(words[:3]) if len(words) > 0 else "response"
        filename_base = (
            filename_base.replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
        )

        md_filename = f"{filename_base}.md"
        send_text_as_file(
            chat_id,
            raw_response,
            md_filename,
        )

        txt_filename = f"{filename_base}.txt"
        plain_text = markdown_to_text(raw_response)
        send_text_as_file(
            chat_id,
            plain_text,
            txt_filename,
        )
    else:
        with SessionLocal() as session:
            user = crud.get_or_create_user(session, user_id)
            search_enabled = user.search_enabled
            current_model = user.current_model
            send_mode = user.send_mode

        bot.send_message(
            chat_id,
            "У меня нет сохраненных ответов для отправки в виде файла.",
            reply_markup=get_main_keyboard(
                send_mode, search_enabled, current_model
            ),
        )


@bot.message_handler(func=lambda message: message.text.startswith("Режим:"))
@ensure_user_started
def handle_send_mode(message):
    """Переключает режим отправки сообщений."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        current_mode = user.send_mode

        new_mode = (
            SEND_MODE_MANUAL
            if current_mode == SEND_MODE_IMMEDIATE
            else SEND_MODE_IMMEDIATE
        )

        updated_user = crud.update_user_send_mode(session, user_id, new_mode)
        new_mode = updated_user.send_mode
        search_enabled = updated_user.search_enabled
        current_model = updated_user.current_model

        # Clear buffer if switching to manual? No, keep it.
        # Clear buffer if switching to immediate? Maybe send existing?
        # Logic says: switching mode just switches future behavior.
        # If switching from manual to immediate, buffer remains until manually cleared or sent.
        # But 'user_message_buffer[user_id] = []' was in original code.
        crud.clear_buffer(session, user_id)

    mode_message = f"Режим отправки изменен на: *{new_mode}*\n\n"
    if new_mode == SEND_MODE_MANUAL:
        mode_message += "Теперь ваши сообщения будут накапливаться. Нажмите кнопку 'Отправить всё', чтобы отправить их в Gemini."
    else:
        mode_message += (
            "Теперь каждое ваше сообщение будет сразу отправляться в Gemini."
        )

    bot.send_message(
        chat_id,
        mode_message,
        reply_markup=get_main_keyboard(
            new_mode, search_enabled, current_model
        ),
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda message: message.text.startswith("Поиск:"))
@ensure_user_started
def handle_search_command(message):
    """Переключает режим поиска Google."""
    user_id = message.from_user.id

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        new_status = not user.search_enabled
        updated_user = crud.update_user_search_enabled(
            session, user_id, new_status
        )

        search_enabled = updated_user.search_enabled
        send_mode = updated_user.send_mode
        current_model = updated_user.current_model

    search_status = "Вкл ✅" if search_enabled else "Выкл ❌"
    bot.reply_to(
        message,
        f"🔎 Поиск Google теперь: *{search_status}*",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(
            send_mode, search_enabled, current_model
        ),
    )


@bot.message_handler(func=lambda message: message.text.startswith("Модель:"))
@ensure_user_started
def select_model(message):
    """Обрабатывает нажатие кнопки "Выбрать модель"."""
    bot.send_message(
        message.chat.id,
        "Выберите модель Gemini:",
        reply_markup=get_model_selection_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == "Отправить всё")
@ensure_user_started
def handle_send_all(message):
    """Отправляет накопленные сообщения (текст и фото) из буфера, сохраняя разрывы между текстами."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        current_mode = user.send_mode
        search_enabled = user.search_enabled
        current_model = user.current_model

    if current_mode != SEND_MODE_MANUAL:
        bot.reply_to(
            message,
            f"Эта кнопка работает только в режиме '{SEND_MODE_MANUAL}'. "
            f"Ваш текущий режим: '{current_mode}'. Используйте /send_mode.",
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )
        return

    buffered_items = get_message_buffer_list(user_id)

    if not buffered_items:
        bot.reply_to(
            message,
            "Буфер сообщений пуст. Нечего отправлять.",
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )
        return

    # Load/Ensure chat exists
    chat_session = get_active_chat(user_id, current_model)

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
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )
        clear_user_context_db(user_id)
        return

    bot.send_chat_action(chat_id, "typing")
    status_msg = bot.reply_to(
        message, "Отправляю накопленные сообщения и фото в Gemini..."
    )

    try:
        if is_image_generation_model(current_model):
            gemini_config = GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        else:
            tools = [Tool(url_context=genai_types.UrlContext())]
            if search_enabled:
                tools.append(Tool(google_search=GoogleSearch()))
            gemini_config = GenerateContentConfig(tools=tools)

        response = chat_session.send_message(
            message=combined_parts, config=gemini_config
        )
        save_active_chat(user_id)  # Save history

        if is_image_generation_model(current_model):
            raw_response_text = send_gemini_response_with_images(
                chat_id, response, reply_to_message_id=message.message_id
            )
        else:
            raw_response_text = response.text

        sources_text = ""
        try:
            if (
                response.candidates
                and response.candidates[0].grounding_metadata
                and response.candidates[0].grounding_metadata.grounding_chunks
            ):
                sources = []
                for i, chunk in enumerate(
                    response.candidates[0].grounding_metadata.grounding_chunks
                ):
                    if (
                        hasattr(chunk, "web")
                        and chunk.web.uri
                        and chunk.web.title
                    ):
                        sources.append(
                            f"{i + 1}. [{chunk.web.title}]({chunk.web.uri})"
                        )
                    elif hasattr(chunk, "web") and chunk.web.uri:
                        sources.append(
                            f"{i + 1}. [{chunk.web.uri}]({chunk.web.uri})"
                        )

                if sources:
                    sources_text = "\n\nИсточники:\n" + "\n".join(sources)
                    raw_response_text += sources_text
        except (AttributeError, IndexError) as e:
            print(f"Не удалось извлечь источники: {e}")

        # Clear buffer after successful send
        with SessionLocal() as session:
            crud.clear_buffer(session, user_id)

        user_last_responses[user_id] = raw_response_text

        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass

        if not is_image_generation_model(current_model):
            plain_response_text = markdown_to_text(raw_response_text)
            message_parts = split_long_message(plain_response_text)

            for i, part in enumerate(message_parts):
                if i == 0:
                    bot.send_message(
                        chat_id, part, reply_to_message_id=message.message_id
                    )
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
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("get_file_")
    or call.data.startswith("get_md_")
)
@ensure_user_started
def handle_get_file(call):
    """Обрабатывает нажатие инлайн кнопок "Получить в виде файла" (.txt или .md)."""

    user_id = int(call.data.split("_")[2])
    file_format = "txt" if call.data.startswith("get_file_") else "md"

    if user_last_responses.get(user_id):
        raw_response = user_last_responses[user_id]

        words = raw_response.split()
        filename = (
            "_".join(words[:3]) + f".{file_format}"
            if len(words) > 0
            else f"response.{file_format}"
        )
        filename = (
            filename.replace("/", "_").replace("\\", "_").replace(":", "_")
        )

        if file_format == "txt":
            file_content = markdown_to_text(raw_response)
            alert_text = "Текстовый файл отправлен!"
        else:
            file_content = raw_response
            alert_text = "Markdown файл отправлен!"

        send_text_as_file(
            call.message.chat.id,
            file_content,
            filename,
        )
        bot.answer_callback_query(call.id, text=alert_text)
    else:
        bot.answer_callback_query(
            call.id,
            text="У меня нет сохраненных ответов для отправки в виде файла.",
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("model_"))
@ensure_user_started
def handle_model_selection(call):
    """Обрабатывает нажатия кнопок выбора модели."""
    user_id = call.from_user.id
    selected_model = call.data.replace("model_", "")

    PRO_MODEL_NAME = "gemini-3.1-pro-preview"
    IMAGE_MODEL_NAME = "gemini-2.5-flash-image"

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)

        if selected_model == PRO_MODEL_NAME and not is_whitelisted(user_id):
            bot.answer_callback_query(
                call.id,
                text="Доступ к про модели ограничен. Используйте /unlock_pro <Имя создателя бота>",
            )
            bot.send_message(
                call.message.chat.id,
                "Доступ к про модели ограничен. Пожалуйста, используйте команду /unlock_pro <Имя создателя бота> для разблокировки.",
                reply_markup=get_main_keyboard(
                    user.send_mode, user.search_enabled, user.current_model
                ),
            )
            return

        if selected_model == IMAGE_MODEL_NAME and not is_whitelisted(user_id):
            bot.answer_callback_query(
                call.id,
                text="Доступ к модели генерации изображений ограничен. Используйте /unlock_pro <Имя создателя бота>",
            )
            bot.send_message(
                call.message.chat.id,
                "Доступ к модели генерации изображений ограничен. Пожалуйста, используйте команду /unlock_pro <Имя создателя бота> для разблокировки.",
                reply_markup=get_main_keyboard(
                    user.send_mode, user.search_enabled, user.current_model
                ),
            )
            return

        updated_user = crud.update_user_model(session, user_id, selected_model)
        current_model = updated_user.current_model
        send_mode = updated_user.send_mode
        search_enabled = updated_user.search_enabled

        # Clear DB session and context when switching models
        crud.clear_chat_session(session, user_id)
        crud.clear_file_contexts(session, user_id)
        crud.clear_buffer(session, user_id)

    # Recreate chat (this will be fresh because we cleared DB)
    if user_id in user_chats:
        del user_chats[user_id]
    get_active_chat(user_id, current_model)

    user_last_responses[user_id] = None

    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"Выбрана модель: {get_model_alias(selected_model)}\n\n"
            f"Контекст предыдущего разговора очищен."
        ),
    )

    bot.send_message(
        call.message.chat.id,
        "Можете начать новый диалог.",
        reply_markup=get_main_keyboard(
            send_mode, search_enabled, current_model
        ),
    )


@bot.message_handler(content_types=["document"])
@ensure_user_started
def handle_document(message):
    """Обрабатывает входящие документы поддерживаемых типов, сохраняя их в контекст."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        current_mode = user.send_mode
        search_enabled = user.search_enabled
        current_model = user.current_model

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
                    reply_markup=get_main_keyboard(
                        current_mode, search_enabled, current_model
                    ),
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

            # Save to DB (File Context)
            add_file_context_entry(user_id, file_data)

            # Get count from DB
            with SessionLocal() as session:
                context_count = len(crud.get_file_contexts(session, user_id))

            if current_mode == SEND_MODE_MANUAL:
                # Add to buffer as well
                add_to_message_buffer(
                    user_id, {**file_data, "type": "document"}
                )

                with SessionLocal() as session:
                    buffer_count = len(crud.get_buffer(session, user_id))

                file_type_short = doc_mime_type.split("/")[-1].upper()
                bot.reply_to(
                    message,
                    f"📄 Файл '{filename}' ({file_type_short}) добавлен в буфер ({buffer_count} шт.). "
                    + ("Подпись также добавлена.\n" if caption else "\n")
                    + f"Всего файлов в контексте: {context_count}.\n"
                    + "Нажмите 'Отправить всё', когда будете готовы.",
                    reply_markup=get_main_keyboard(
                        current_mode, search_enabled, current_model
                    ),
                )
            else:
                file_type_short = doc_mime_type.split("/")[-1].upper()
                bot.reply_to(
                    message,
                    f"✅ Файл '{filename}' ({file_type_short}) добавлен в контекст (всего: {context_count}). "
                    "Он будет автоматически использован при следующем текстовом запросе.",
                    reply_markup=get_main_keyboard(
                        current_mode, search_enabled, current_model
                    ),
                )

        except Exception as e:
            bot.reply_to(
                message,
                f"Не удалось обработать файл '{message.document.file_name}': {e!s}",
                reply_markup=get_main_keyboard(
                    current_mode, search_enabled, current_model
                ),
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
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )


@bot.message_handler(content_types=["photo"])
@ensure_user_started
def handle_photo(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        current_mode = user.send_mode
        search_enabled = user.search_enabled
        current_model = user.current_model

    file_id = message.photo[-1].file_id
    caption = message.caption if message.caption else ""
    if current_mode == SEND_MODE_MANUAL:
        try:
            bot.send_chat_action(chat_id, "typing")
            image_stream = download_telegram_image(file_id)
            img = Image.open(image_stream)

            add_to_message_buffer(
                user_id, {"type": "photo", "image": img, "caption": caption}
            )

            with SessionLocal() as session:
                buffer_count = len(crud.get_buffer(session, user_id))

            bot.reply_to(
                message,
                f"Фото добавлено в буфер ({buffer_count} шт.). "
                + ("Подпись также добавлена.\n" if caption else "\n")
                + "Нажмите 'Отправить всё', когда будете готовы.",
                reply_markup=get_main_keyboard(
                    current_mode, search_enabled, current_model
                ),
            )
        except Exception as e:
            bot.reply_to(
                message,
                f"Не удалось добавить фото в буфер: {e!s}",
                reply_markup=get_main_keyboard(
                    current_mode, search_enabled, current_model
                ),
            )
        return

    chat_session = get_active_chat(user_id, current_model)

    bot.send_chat_action(chat_id, "typing")
    try:
        image_stream = download_telegram_image(file_id)
        img = Image.open(image_stream)

        api_message_parts = []

        if caption:
            api_message_parts.append(caption)
        api_message_parts.append(img)

        if is_image_generation_model(current_model):
            gemini_config = GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
            response = chat_session.send_message(
                message=api_message_parts, config=gemini_config
            )
        else:
            response = chat_session.send_message(message=api_message_parts)
        save_active_chat(user_id)  # Save

        if is_image_generation_model(current_model):
            raw_response_text = send_gemini_response_with_images(
                chat_id, response, reply_to_message_id=message.message_id
            )
        else:
            raw_response_text = response.text

        user_last_responses[user_id] = raw_response_text

        if not is_image_generation_model(current_model):
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
                    "Ответ был разбит на несколько сообщений.",
                    reply_markup=get_file_download_keyboard(user_id),
                )

    except Exception as e:
        bot.reply_to(
            message,
            f"Произошла ошибка при обработке изображения ({current_model}): {e!s}\n\n"
            "Возможно, стоит попробовать новый чат.",
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )


@bot.message_handler(
    func=lambda message: message.text
    and message.text.startswith("/")
    and message.text.split(" ", 1)[0][1:] in QUICK_TOOLS_CONFIG
)
@ensure_user_started
def handle_quick_tool_command(message):
    """Обрабатывает команды быстрых инструментов (напр., /translate, /prompt)."""
    chat_id = message.chat.id
    command_with_slash = message.text.split(" ", 1)[0]
    command = command_with_slash[1:]
    user_query = (
        message.text.split(" ", 1)[1].strip() if " " in message.text else ""
    )

    if not user_query:
        bot.reply_to(
            message,
            f"Пожалуйста, укажите текст после команды {command_with_slash}.\n"
            f"Например: `{command_with_slash} ваш текст здесь`",
            parse_mode="Markdown",
        )
        return

    tool_config = QUICK_TOOLS_CONFIG[command]
    system_instruction = tool_config["system_instruction"]
    model_to_use = tool_config.get("model", DEFAULT_MODEL)
    thinking_budget = tool_config.get("thinking_budget", None)

    bot.send_chat_action(chat_id, "typing")
    status_msg = bot.reply_to(
        message, f"Выполняю команду `{command_with_slash}`..."
    )

    if len(user_query) > 4000:
        bot.reply_to(
            message,
            f"Текст слишком длинный для команды {command_with_slash}. Максимум 4000 символов.",
        )
        return

    try:
        config_kwargs = {"system_instruction": system_instruction}
        if (
            model_to_use == "gemini-3-flash-preview"
            and thinking_budget is not None
        ):
            config_kwargs["thinking_config"] = genai_types.ThinkingConfig(
                thinking_budget=thinking_budget
            )

        if is_image_generation_model(model_to_use):
            config_kwargs["response_modalities"] = ["TEXT", "IMAGE"]

        response = client.models.generate_content(
            model=model_to_use,
            contents=user_query,
            config=genai_types.GenerateContentConfig(**config_kwargs),
        )

        if is_image_generation_model(model_to_use):
            raw_response_text = send_gemini_response_with_images(
                chat_id, response, reply_to_message_id=message.message_id
            )
        else:
            raw_response_text = response.text

        if command in ["todo", "markdown", "dayplanner"]:
            words = user_query.split()
            filename_base = "_".join(words[:3]) if len(words) > 0 else command
            filename = f"{filename_base}_{command}.md"
            filename = (
                filename.replace("/", "_").replace("\\", "_").replace(":", "_")
            )
            send_text_as_file(chat_id, raw_response_text, filename)

        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass

        if not is_image_generation_model(model_to_use):
            plain_response_text = markdown_to_text(raw_response_text)
            message_parts = split_long_message(plain_response_text)

            for i, part in enumerate(message_parts):
                if i == 0:
                    bot.reply_to(message, part)
                else:
                    bot.send_message(chat_id, part)

    except Exception as e:
        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass
        print(f"Error in quick tool command '{command}': {e}")
        bot.reply_to(
            message,
            f"Произошла ошибка при выполнении команды `{command_with_slash}`: {e!s}",
        )


@bot.message_handler(func=lambda message: True)
@ensure_user_started
def handle_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        current_mode = user.send_mode
        search_enabled = user.search_enabled
        current_model = user.current_model

    if current_mode == SEND_MODE_MANUAL:
        # Add to buffer in DB
        add_to_message_buffer(
            user_id, {"type": "text", "content": message.text}
        )

        with SessionLocal() as session:
            buffer_count = len(crud.get_buffer(session, user_id))

        bot.reply_to(
            message,
            f"Сообщение добавлено в буфер ({buffer_count} шт.). Нажмите 'Отправить всё', когда будете готовы.",
        )
        return

    bot.send_chat_action(message.chat.id, "typing")

    try:

        api_message_parts = []

        files_in_context = get_file_context_list(user_id)
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
                            mime_type=file_info["mime_type"],
                            data=file_info["data"],
                        )
                    )

                    api_message_parts.append(
                        f"(Файл: {file_info['filename']})"
                    )
                except Exception as file_err:
                    bot.send_message(
                        chat_id,
                        f"⚠️ Не удалось добавить файл '{file_info['filename']}' в запрос: {file_err}",
                    )

        api_message_parts.append(message.text)

        # Load chat from cache or DB
        chat_session = get_active_chat(user_id, current_model)

        if is_image_generation_model(current_model):
            gemini_config = GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        else:
            tools = [Tool(url_context=genai_types.UrlContext())]
            if search_enabled:
                tools.append(Tool(google_search=GoogleSearch()))
            gemini_config = GenerateContentConfig(tools=tools)

        response = chat_session.send_message(
            message=api_message_parts, config=gemini_config
        )
        save_active_chat(user_id)  # Save history

        # Clear file contexts after successful immediate-mode send
        if files_in_context:
            with SessionLocal() as session:
                crud.clear_file_contexts(session, user_id)
        if is_image_generation_model(current_model):
            raw_response_text = send_gemini_response_with_images(
                message.chat.id,
                response,
                reply_to_message_id=message.message_id,
            )
        else:
            raw_response_text = response.text

        sources_text = ""
        try:
            if (
                response.candidates
                and response.candidates[0].grounding_metadata
                and response.candidates[0].grounding_metadata.grounding_chunks
            ):
                sources = []
                for i, chunk in enumerate(
                    response.candidates[0].grounding_metadata.grounding_chunks
                ):
                    if (
                        hasattr(chunk, "web")
                        and chunk.web.uri
                        and chunk.web.title
                    ):
                        sources.append(
                            f"{i + 1}. [{chunk.web.title}]({chunk.web.uri})"
                        )
                    elif hasattr(chunk, "web") and chunk.web.uri:
                        sources.append(
                            f"{i + 1}. [{chunk.web.uri}]({chunk.web.uri})"
                        )

                if sources:
                    sources_text = "\n\nИсточники:\n" + "\n".join(sources)
                    raw_response_text += sources_text
        except (AttributeError, IndexError) as e:
            print(f"Не удалось извлечь источники: {e}")

        user_last_responses[user_id] = raw_response_text

        if not is_image_generation_model(current_model):
            plain_response_text = (
                markdown_to_text(response.text) + sources_text
            )
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
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )


if __name__ == "__main__":
    db.init_db()
    load_whitelist()
    bot.polling(none_stop=True)
