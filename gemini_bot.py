import ipv4_only  # noqa: F401 E261
import io
import json
import base64

import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from PIL import Image

from constants import (
    ADMIN_IDS,
    COMMAND_LIST,
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
from threading import Lock, RLock

from utils import (
    markdown_to_text,
    send_rich_response,
)

from database import db, crud
from database import model_catalog
from database.db import SessionLocal
from admin import register_admin_handlers
from inline_bot import register_inline_handlers
from usage import track_gemini_call
from chat_activity import typing_action
from chat_context import serialize_history, portable_history, context_contents, contains_audio

load_dotenv()

client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

bot.set_my_commands(COMMAND_LIST)

# Register before general message handlers.
register_admin_handlers(bot, SessionLocal, model_client=client)
inline_panel = register_inline_handlers(bot, client, SessionLocal)

# Global stores
user_chats = {}  # Cache for active chat sessions
user_last_responses = {}
_user_operation_locks = {}
_user_operation_registry_lock = Lock()


class HistoryRestoreError(ValueError):
    """Saved conversation cannot safely be restored without losing content."""


class UserRequestError(ValueError):
    """A local validation message that is safe to show to the user."""


class ModelAccessError(PermissionError):
    """A local model access failure that is safe to show to the user."""


def request_error_message(error):
    if isinstance(error, (HistoryRestoreError, UserRequestError, ModelAccessError)):
        return str(error)
    # Provider/network exceptions may contain credentials in request URLs.
    print(f"Request failed: {type(error).__name__}")
    return "Не удалось выполнить запрос. Попробуйте позже."


def history_error(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("Новый чат"))
    bot.send_message(
        chat_id,
        "Не удалось восстановить сохранённую историю. Она не изменена. "
        "Для явного сброса нажмите «Новый чат».",
        reply_markup=markup,
    )


def serialize_user_operation(func):
    """Finish a user's current request before switching or resetting its chat."""
    @wraps(func)
    def serialized(message, *args, **kwargs):
        actor = getattr(message, "from_user", None)
        if actor is None:
            return func(message, *args, **kwargs)
        with _user_operation_registry_lock:
            lock = _user_operation_locks.setdefault(actor.id, RLock())
        if isinstance(message, telebot.types.CallbackQuery):
            if not lock.acquire(blocking=False):
                bot.answer_callback_query(
                    message.id, text="Дождитесь завершения текущего запроса."
                )
                return None
            try:
                return func(message, *args, **kwargs)
            finally:
                lock.release()
        with lock:
            return func(message, *args, **kwargs)
    return serialized


# --- Helper Functions for Persistence ---


def generate_with_typing(chat_id, user_id, model_name, operation, api_call, *args, **kwargs):
    # Recheck after preparing uploads/config: admin policy may have changed.
    with SessionLocal() as session:
        if not model_catalog.can_use_model(
            session, model_name, crud.has_pro_access(session, user_id), is_admin=user_id in ADMIN_IDS,
        ):
            raise ModelAccessError("Доступ к модели изменился. Выберите доступную модель в меню.")
    chat = user_chats.get(user_id)
    if (operation in ('chat', 'photo', 'buffer') and is_image_generation_model(model_name)
            and chat is not None and contains_audio(chat.get_history(curated=True))):
        raise UserRequestError("В истории есть голосовые. Выберите текстовую модель или начните новый чат; история и буфер сохранены.")
    with typing_action(bot, chat_id):
        response = track_gemini_call(user_id, model_name, operation, api_call, *args, **kwargs)
    if operation in ('chat', 'photo', 'buffer', 'voice'):
        candidates = getattr(response, 'candidates', None) or []
        content = candidates[0].content if candidates else None
        parts = getattr(content, 'parts', None) or []
        # The SDK retains only candidate 0, and excludes turns containing an
        # empty part from curated history. Such a response cannot consume input.
        valid_turn = bool(parts and all(part != genai_types.Part() for part in parts))
        text = getattr(response, 'text', None)
        has_text = isinstance(text, str) and bool(text.strip())
        has_image = is_image_generation_model(model_name) and any(
            part.inline_data and part.inline_data.data
            and (part.inline_data.mime_type or '').startswith('image/')
            for part in parts
            if not part.thought
        )
        if not valid_turn or not (has_text or has_image):
            raise UserRequestError(
                "Модель не вернула ответ. Ожидающие файлы и буфер сохранены; "
                "попробуйте переформулировать запрос."
            )
    return response


def deserialize_history(history_json):
    """Deserializes JSON history into list of types.Content."""
    if not history_json:
        return []
    try:
        data = json.loads(history_json)
        if not isinstance(data, list):
            raise ValueError("History must be a list")
        history = []
        for item in data:
            if (not isinstance(item, dict) or item.get('role') not in ('user', 'model')
                    or not isinstance(item.get('parts'), list)):
                raise ValueError("Invalid saved content")
            parts = []
            for part_data in item.get("parts", []):
                if not isinstance(part_data, dict):
                    raise ValueError("Invalid saved part")
                if "inline_data" in part_data and part_data["inline_data"]:
                    blob_data = part_data["inline_data"]
                    if "data" in blob_data and isinstance(
                        blob_data["data"], str
                    ):
                        try:
                            blob_data["data"] = base64.b64decode(blob_data["data"], validate=True)
                        except Exception as error:
                            raise ValueError("Invalid saved media") from error
                signature = part_data.get("thought_signature")
                if isinstance(signature, str):
                    part_data["thought_signature"] = base64.b64decode(signature, validate=True)
                parts.append(genai_types.Part(**part_data))
            history.append(
                genai_types.Content(role=item.get("role"), parts=parts)
            )
        return history
    except Exception as error:
        raise HistoryRestoreError("Не удалось восстановить сохранённую историю. Она не изменена.") from error


def ensure_user_model(session, user):
    """Apply current model availability and access to saved user settings."""
    model_name = model_catalog.resolve_model(
        session, user.current_model, user.pro_access, is_admin=user.id in ADMIN_IDS,
    )
    if model_name != user.current_model:
        cached = user_chats.get(user.id)
        if cached is not None and hasattr(cached, "get_history"):
            history = cached.get_history(curated=True)
        else:
            saved = crud.get_chat_session(session, user.id)
            history = deserialize_history(saved.history_json) if saved else []
        user = crud.switch_user_model(
            session, user.id, model_name, serialize_history(portable_history(history))
        )
        user_chats.pop(user.id, None)
    return user


def get_active_chat(user_id, model_name):
    """Gets active chat from cache or loads from DB."""
    if user_id in user_chats:
        return user_chats[user_id]

    with SessionLocal() as session:
        chat_session = crud.get_chat_session(session, user_id)
        history = []
        if chat_session and chat_session.history_json:
            history = deserialize_history(chat_session.history_json)

    # Never silently discard a saved conversation when restoration fails.
    try:
        new_chat = client.chats.create(model=model_name, history=history)
    except ValueError as error:
        if history:
            raise HistoryRestoreError("Не удалось восстановить сохранённую историю. Она не изменена.") from error
        raise
    user_chats[user_id] = new_chat
    return new_chat


def save_active_chat(user_id, *, clear_files=False, clear_buffer=False):
    """Save history and consume pending inputs together, or leave both intact."""
    try:
        chat = user_chats[user_id]
        history = chat.get_history(curated=True)
        history_json = serialize_history(history)
        with SessionLocal() as session:
            crud.save_chat_session(
                session, user_id, history_json, clear_files=clear_files, clear_buffer=clear_buffer,
            )
    except Exception:
        user_chats.pop(user_id, None)
        raise


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
            elif item.item_type in ("document", "voice"):
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
        elif entry["type"] in ("document", "voice"):
            crud.add_to_buffer(
                session,
                user_id,
                entry["type"],
                content=entry.get("caption"),
                blob_data=entry["data"],
                filename=entry["filename"],
                mime_type=entry["mime_type"],
            )


def clear_user_context_db(user_id):
    with SessionLocal() as session:
        crud.clear_user_context(session, user_id)


def add_to_whitelist(user_id):
    """Persist premium access in the users table."""
    with SessionLocal() as session:
        crud.set_user_pro_access(session, user_id, True)


def is_whitelisted(user_id):
    """Read access from the database so changes apply immediately."""
    with SessionLocal() as session:
        return crud.has_pro_access(session, user_id)


def ensure_user_started(func):
    """Декоратор: проверяет, начал ли пользователь диалог командой /start (есть ли в БД)."""

    @wraps(func)
    @serialize_user_operation
    def wrapper(message, *args, **kwargs):
        if isinstance(message, telebot.types.CallbackQuery):
            if message.message is None:
                bot.answer_callback_query(message.id, text="Откройте личный чат с ботом.")
                return None
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
            user = crud.record_user_activity(session, message.from_user)
            previous_model = user.current_model
            try:
                if func.__name__ != 'new_chat':
                    user = ensure_user_model(session, user)
            except HistoryRestoreError:
                if is_callback:
                    bot.answer_callback_query(message.id)
                history_error(chat_id)
                return None
            model_changed = user.current_model != previous_model
            current_model = user.current_model
            markup = get_main_keyboard(user.send_mode, user.search_enabled, current_model) if model_changed else None
        if model_changed:
            bot.send_message(
                chat_id,
                f"Выбранная модель больше недоступна. Теперь выбрана {get_model_alias(current_model)}.\n"
                "История, файлы и буфер сохранены.",
                reply_markup=markup,
            )
        return func(message, *args, **kwargs)

    return wrapper


def download_telegram_image(file_id):
    """Загружает изображение из Telegram."""
    try:
        file_info = bot.get_file(file_id)
        limit = MAX_FILE_SIZE_MB * 1024 * 1024
        if (file_info.file_size or 0) > limit:
            raise ValueError("Image too large")
        data = bot.download_file(file_info.file_path)
        if not data or len(data) > limit:
            raise ValueError("Invalid image size")
        return io.BytesIO(data)
    except Exception as error:
        # Telegram download exceptions may contain the full URL with bot token.
        print(f"Could not download photo: {type(error).__name__}")
        raise UserRequestError(f"Не удалось загрузить фото. Максимум {MAX_FILE_SIZE_MB} МБ. Попробуйте ещё раз.") from None


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
                                print(f"Could not deliver generated image: {type(e).__name__}")
                                text_parts.append(
                                    "[Не удалось отправить изображение. Попробуйте ещё раз позже.]"
                                )

    if not text_parts and hasattr(response, "text") and response.text:
        text_parts.append(response.text)

    if text_parts:
        combined_text = "\n".join(text_parts)
        send_rich_response(
            bot,
            chat_id,
            combined_text,
            reply_to_message_id=reply_to_message_id,
        )
        return combined_text

    return ""


@bot.message_handler(commands=["help"])
@serialize_user_operation
def handle_help_command(message):
    """Выводит подробную справку по функциям бота."""
    with SessionLocal() as session:
        crud.record_user_activity(session, message.from_user)
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

    if (
        PRO_CODE
        and len(command_parts) == 2
        and command_parts[1].strip() == PRO_CODE
    ):
        add_to_whitelist(user_id)
        bot.reply_to(message, "✅ Доступ к моделям для белого списка разблокирован!")
    else:
        bot.reply_to(message, "❌ Неверный код. Используйте другой")


@bot.message_handler(commands=["start"])
@serialize_user_operation
def send_welcome(message):
    """Обрабатывает команду /start."""
    user_id = message.from_user.id

    try:
        with SessionLocal() as session:
            user = ensure_user_model(
                session, crud.record_user_activity(session, message.from_user)
            )
            current_model = user.current_model
            send_mode = user.send_mode
            search_enabled = user.search_enabled
        get_active_chat(user_id, current_model)
    except HistoryRestoreError:
        history_error(message.chat.id)
        return

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
        current_model = model_catalog.resolve_model(
            session, user.current_model, user.pro_access, is_admin=user_id in ADMIN_IDS,
        )
        send_mode = user.send_mode
        search_enabled = user.search_enabled

        # Prepare first; a local SDK failure must not erase the stored dialogue.
        try:
            replacement = client.chats.create(model=current_model, history=[])
            user.current_model = current_model
            crud.clear_user_context(session, user_id, clear_history=True)
        except Exception as error:
            print(f"Could not reset chat: {type(error).__name__}")
            bot.reply_to(message, "Не удалось начать новый чат. Прежняя история и вложения сохранены.")
            return
    user_chats[user_id] = replacement

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
    if chat_id != user_id:
        bot.reply_to(message, "Скачивание ответов доступно в личном чате с ботом.")
        return

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

        pending_count = len(crud.get_buffer(session, user_id))

    mode_message = f"Режим отправки изменен на: *{new_mode}*\n\n"
    if new_mode == SEND_MODE_MANUAL:
        mode_message += "Теперь ваши сообщения будут накапливаться. Нажмите кнопку 'Отправить всё', чтобы отправить их в Gemini."
    else:
        mode_message += (
            "Теперь каждое ваше сообщение будет сразу отправляться в Gemini."
        )
        if pending_count:
            mode_message += f"\nБуфер ({pending_count} шт.) сохранён. Для отправки вернитесь в ручной режим."

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


@bot.message_handler(commands=["context"])
@bot.message_handler(func=lambda message: message.text == "Контекст 🧠")
@ensure_user_started
def show_context_size(message):
    user_id = message.from_user.id
    with SessionLocal() as session:
        user = crud.get_user(session, user_id)
        model = user.current_model
    try:
        history = get_active_chat(user_id, model).get_history(curated=True)
        files = get_file_context_list(user_id)
        buffer = get_message_buffer_list(user_id)
        contents = context_contents(history, files, buffer)
        total = client.models.count_tokens(model=model, contents=contents).total_tokens if contents else 0
        if not isinstance(total, int) or total < 0:
            raise ValueError("No token count returned")
        limit = None
        try:
            limit = client.models.get(model=model).input_token_limit
        except Exception:
            pass
        lines = [f"Контекст 🧠 · {get_model_alias(model)}", f"Размер: ≈{total:,} токенов".replace(",", " ")]
        if isinstance(limit, int) and limit > 0:
            lines.append(f"Лимит входа: {limit:,} · заполнено ≈{total / limit:.1%}".replace(",", " "))
        lines.extend([
            f"Сообщений в истории: {len(history)}",
            f"Ожидающих файлов: {len(files)} · Элементов буфера: {len(buffer)}",
            "Включены история, ожидающие файлы и буфер. Следующее сообщение и служебные инструменты не включены.",
            "Для очистки нажмите «Новый чат».",
        ])
        bot.reply_to(message, "\n".join(lines))
    except Exception as error:
        print(f"Could not count context: {type(error).__name__}")
        bot.reply_to(message, "Не удалось посчитать контекст. Попробуйте позже; история сохранена.")


@bot.message_handler(func=lambda message: message.text.startswith("Модель:"))
@ensure_user_started
def select_model(message):
    """Обрабатывает нажатие кнопки "Выбрать модель"."""
    with SessionLocal() as session:
        is_admin = message.from_user.id in ADMIN_IDS
        models = model_catalog.list_models(session, include_disabled=False, is_admin=is_admin)
        markup = get_model_selection_keyboard(
            models, has_pro_access=crud.has_pro_access(session, message.from_user.id), is_admin=is_admin,
        )
    bot.send_message(
        message.chat.id,
        "Выберите модель Gemini:",
        reply_markup=markup,
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

    try:
        buffered_items = get_message_buffer_list(user_id)
        files_in_context = get_file_context_list(user_id)
    except Exception as error:
        print(f"Could not load pending context: {type(error).__name__}")
        bot.reply_to(message, "Не удалось прочитать буфер. Данные сохранены; попробуйте позже.")
        return

    if not buffered_items:
        bot.reply_to(
            message,
            "Буфер сообщений пуст. Нечего отправлять.",
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )
        return

    has_voice = any(item["type"] == "voice" for item in buffered_items)
    if has_voice and is_image_generation_model(current_model):
        bot.reply_to(message, "Для голосовых выберите текстовую модель с поддержкой аудио. Буфер сохранён.")
        return

    # Load/Ensure chat exists
    try:
        chat_session = get_active_chat(user_id, current_model)
        # Older versions stored manual documents twice. Send them only once.
        buffered_documents = {
            (item['filename'], item['mime_type'], item['data'], item.get('caption') or '')
            for item in buffered_items if item['type'] == 'document'
        }
        pending_files = [item for item in files_in_context if
                         (item['filename'], item['mime_type'], item['data'], item.get('caption') or '')
                         not in buffered_documents]
        pending = context_contents([], pending_files, [])
        combined_parts = list(pending[0].parts) if pending else []
    except HistoryRestoreError:
        history_error(chat_id)
        return
    except Exception as error:
        print(f"Could not prepare pending context: {type(error).__name__}")
        bot.reply_to(message, "Не удалось подготовить вложения. Буфер и файлы сохранены.")
        return
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
        elif item["type"] == "voice":
            if current_text_block:
                combined_parts.append(current_text_block)
                current_text_block = ""
            combined_parts.append(genai_types.Part.from_bytes(
                mime_type=item["mime_type"], data=item["data"]
            ))
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
                print(f"Could not prepare buffered file: {type(file_err).__name__}")
                bot.send_message(
                    chat_id,
                    f"⚠️ Не удалось добавить файл '{item['filename']}' в запрос. Буфер сохранён.",
                )
                return

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
        return

    status_msg = bot.reply_to(
        message, "Отправляю накопленные сообщения и вложения в Gemini..."
    )

    history_saved = False
    try:
        if is_image_generation_model(current_model):
            gemini_config = GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        else:
            tools = [Tool(url_context=genai_types.UrlContext())]
            if search_enabled:
                tools.append(Tool(google_search=GoogleSearch()))
            gemini_config = GenerateContentConfig(
                tools=tools,
                response_modalities=["TEXT"] if has_voice else None,
                system_instruction=VOICE_INSTRUCTION if has_voice else None,
            )

        response = generate_with_typing(
            chat_id,
            user_id, current_model, "buffer", chat_session.send_message,
            message=combined_parts, config=gemini_config
        )
        save_active_chat(user_id, clear_files=bool(files_in_context), clear_buffer=True)
        history_saved = True

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

        user_last_responses[user_id] = raw_response_text

        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass

        if not is_image_generation_model(current_model):
            send_rich_response(
                bot,
                chat_id,
                raw_response_text,
                reply_to_message_id=message.message_id,
                fallback_download_keyboard=get_file_download_keyboard(user_id),
            )

    except Exception as e:
        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass
        bot.reply_to(
            message,
            f"{request_error_message(e)}\n\n"
            + ("Запрос уже обработан и сохранён в истории. Повторная отправка буфера не нужна."
               if history_saved else "Ваши сообщения и вложения сохранены. Попробуйте позже."),
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )


@bot.callback_query_handler(
    func=lambda call: (
        bool(call.data) and (call.data.startswith("get_file_") or call.data.startswith("get_md_"))
    )
)
@ensure_user_started
def handle_get_file(call):
    """Обрабатывает нажатие инлайн кнопок "Получить в виде файла" (.txt или .md)."""

    data = call.data or ''
    prefix = 'get_file_' if data.startswith('get_file_') else 'get_md_'
    identifier = data.removeprefix(prefix)
    actor_id = call.from_user.id
    chat = getattr(getattr(call, 'message', None), 'chat', None)
    if (not data.startswith(prefix) or not identifier.isascii() or not identifier.isdecimal()
            or len(identifier) > 19 or int(identifier) >= 2**63
            or int(identifier) != actor_id or getattr(chat, 'id', None) != actor_id):
        bot.answer_callback_query(call.id, text="Скачивать можно только свои ответы в личном чате с ботом.")
        return
    user_id = actor_id
    file_format = "txt" if prefix == 'get_file_' else "md"

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


@bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("model_")))
@ensure_user_started
def handle_model_selection(call):
    """Обрабатывает нажатия кнопок выбора модели."""
    user_id = call.from_user.id
    with SessionLocal() as session:
        user = crud.get_or_create_user(session, user_id)
        if call.data.startswith('model_id_'):
            identifier = call.data.removeprefix('model_id_')
            model = (model_catalog.get_model_by_id(session, int(identifier))
                     if identifier.isascii() and identifier.isdecimal() and len(identifier) <= 18 else None)
        else:
            # Old keyboards remain valid only while the current policy permits them.
            model = model_catalog.get_model(session, call.data.removeprefix('model_'))
        if model is None or model.access == 'disabled' or (model.access == 'admin' and user_id not in ADMIN_IDS):
            bot.answer_callback_query(
                call.id, text="Эта модель больше недоступна. Выберите модель из меню."
            )
            return
        selected_model = model.name
        if not model_catalog.can_use_model(
            session, selected_model, user.pro_access, is_admin=user_id in ADMIN_IDS,
        ):
            bot.answer_callback_query(
                call.id,
                text="Доступ ограничен. Используйте /unlock_pro <код>",
            )
            bot.send_message(
                call.message.chat.id,
                "Для доступа к закрытым моделям используйте /unlock_pro <код>.",
                reply_markup=get_main_keyboard(
                    user.send_mode, user.search_enabled, user.current_model
                ),
            )
            return

        if selected_model == user.current_model:
            bot.answer_callback_query(call.id, text="Эта модель уже выбрана.")
            return
        try:
            old_chat = get_active_chat(user_id, user.current_model)
            history = portable_history(old_chat.get_history(curated=True))
            if is_image_generation_model(selected_model) and contains_audio(history):
                bot.answer_callback_query(
                    call.id,
                    text="В истории есть голосовые. Для модели изображений начните новый чат.",
                    show_alert=True,
                )
                return
            new_chat = client.chats.create(model=selected_model, history=history)
            updated_user = crud.switch_user_model(
                session, user_id, selected_model, serialize_history(history)
            )
        except Exception as error:
            print(f"Could not switch model: {type(error).__name__}")
            bot.answer_callback_query(call.id, text="Не удалось сменить модель. Попробуйте позже.")
            return
        current_model = updated_user.current_model
        send_mode = updated_user.send_mode
        search_enabled = updated_user.search_enabled

    user_chats[user_id] = new_chat

    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"Выбрана модель: {get_model_alias(selected_model)}\n\n"
            f"История, файлы и буфер сохранены."
        ),
    )

    bot.send_message(
        call.message.chat.id,
        "Можете продолжить диалог.",
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

            if (file_info.file_size or 0) > MAX_FILE_SIZE_MB * 1024 * 1024:
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
            if not downloaded_file or len(downloaded_file) > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise UserRequestError(f"Не удалось прочитать документ. Максимум {MAX_FILE_SIZE_MB} МБ.")
            pdf_bytes = downloaded_file
            filename = message.document.file_name
            caption = message.caption or ""

            file_data = {
                "mime_type": doc_mime_type,
                "data": pdf_bytes,
                "filename": filename,
                "caption": caption,
            }

            if current_mode == SEND_MODE_MANUAL:
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
                    + "Нажмите 'Отправить всё', когда будете готовы.",
                    reply_markup=get_main_keyboard(
                        current_mode, search_enabled, current_model
                    ),
                )
            else:
                add_file_context_entry(user_id, file_data)
                with SessionLocal() as session:
                    context_count = len(crud.get_file_contexts(session, user_id))
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
                f"Не удалось обработать файл '{message.document.file_name}'. {request_error_message(e)}",
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


VOICE_INSTRUCTION = (
    "Treat the voice recording as a normal user message in this conversation. "
    "Answer its question or carry out its request rather than merely transcribing it. "
    "Reply in text in the user's language."
)


@bot.message_handler(content_types=["voice"])
@ensure_user_started
def handle_voice(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    with SessionLocal() as session:
        user = crud.get_user(session, user_id)
        current_model, current_mode = user.current_model, user.send_mode
        search_enabled = user.search_enabled
    if is_image_generation_model(current_model):
        bot.reply_to(message, "Для голосовых выберите текстовую модель с поддержкой аудио.")
        return
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if (message.voice.file_size or 0) > max_bytes:
        bot.reply_to(message, f"Голосовое слишком большое. Максимум {MAX_FILE_SIZE_MB} МБ.")
        return
    try:
        file_info = bot.get_file(message.voice.file_id)
        if (file_info.file_size or 0) > max_bytes:
            bot.reply_to(message, f"Голосовое слишком большое. Максимум {MAX_FILE_SIZE_MB} МБ.")
            return
        data = bot.download_file(file_info.file_path)
        if not data or len(data) > max_bytes:
            bot.reply_to(message, f"Не удалось прочитать голосовое. Максимум {MAX_FILE_SIZE_MB} МБ.")
            return
        mime_type = message.voice.mime_type or "audio/ogg"
        if current_mode == SEND_MODE_MANUAL:
            add_to_message_buffer(user_id, {
                "type": "voice", "data": data, "mime_type": mime_type,
                "filename": "voice", "caption": "",
            })
            with SessionLocal() as session:
                count = len(crud.get_buffer(session, user_id))
            bot.reply_to(message, f"🎤 Голосовое добавлено в буфер ({count} шт.). Нажмите «Отправить всё».")
            return
        files = get_file_context_list(user_id)
        pending = context_contents([], files, [])
        parts = list(pending[0].parts) if pending else []
        parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime_type))
        tools = [Tool(url_context=genai_types.UrlContext())]
        if search_enabled:
            tools.append(Tool(google_search=GoogleSearch()))
        chat = get_active_chat(user_id, current_model)
        response = generate_with_typing(
            chat_id,
            user_id, current_model, "voice", chat.send_message,
            message=parts,
            config=GenerateContentConfig(
                response_modalities=["TEXT"], system_instruction=VOICE_INSTRUCTION, tools=tools,
            ),
        )
        save_active_chat(user_id, clear_files=bool(files))
        text = response.text
        if not text:
            bot.reply_to(message, "Модель не вернула текстовый ответ. Попробуйте переформулировать голосовое.")
            return
        user_last_responses[user_id] = text
        send_rich_response(
            bot, chat_id, text, reply_to_message_id=message.message_id,
            fallback_download_keyboard=get_file_download_keyboard(user_id),
        )
    except Exception as error:
        print(f"Could not process voice message: {type(error).__name__}")
        bot.reply_to(message, "Не удалось обработать голосовое. Попробуйте отправить его ещё раз.")


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
                f"Не удалось добавить фото в буфер. {request_error_message(e)}",
                reply_markup=get_main_keyboard(
                    current_mode, search_enabled, current_model
                ),
            )
        return

    try:
        chat_session = get_active_chat(user_id, current_model)
        image_stream = download_telegram_image(file_id)
        img = Image.open(image_stream)

        files = get_file_context_list(user_id)
        pending = context_contents([], files, [])
        api_message_parts = list(pending[0].parts) if pending else []

        if caption:
            api_message_parts.append(caption)
        api_message_parts.append(img)

        if is_image_generation_model(current_model):
            gemini_config = GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
            response = generate_with_typing(
                chat_id,
                user_id, current_model, "photo", chat_session.send_message,
                message=api_message_parts, config=gemini_config
            )
        else:
            response = generate_with_typing(
                chat_id,
                user_id, current_model, "photo", chat_session.send_message,
                message=api_message_parts,
            )
        save_active_chat(user_id, clear_files=bool(files))

        if is_image_generation_model(current_model):
            raw_response_text = send_gemini_response_with_images(
                chat_id, response, reply_to_message_id=message.message_id
            )
        else:
            raw_response_text = response.text

        user_last_responses[user_id] = raw_response_text

        if not is_image_generation_model(current_model):
            send_rich_response(
                bot,
                chat_id,
                raw_response_text,
                reply_to_message_id=message.message_id,
                fallback_download_keyboard=get_file_download_keyboard(user_id),
            )

    except Exception as e:
        bot.reply_to(
            message,
            f"Не удалось обработать изображение ({current_model}). {request_error_message(e)}\n\n"
            "Возможно, стоит попробовать новый чат.",
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )


@bot.message_handler(
    func=lambda message: (
        message.text
        and message.text.startswith("/")
        and message.text.split(" ", 1)[0][1:] in QUICK_TOOLS_CONFIG
    )
)
@ensure_user_started
def handle_quick_tool_command(message):
    """Обрабатывает команды быстрых инструментов (напр., /translate, /prompt)."""
    chat_id = message.chat.id
    user_id = message.from_user.id
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
    with SessionLocal() as session:
        model_to_use = tool_config.get("model") or model_catalog.get_default_model(session)
        model = model_catalog.get_model(session, model_to_use)
        if model is None or model.access == 'disabled':
            bot.reply_to(message, "Модель этой команды отключена. Обратитесь к администратору.")
            return
        if model.access == 'admin' and user_id not in ADMIN_IDS:
            bot.reply_to(message, "Эта команда доступна только администратору.")
            return
        if not model_catalog.can_use_model(
            session, model_to_use, crud.has_pro_access(session, user_id), is_admin=user_id in ADMIN_IDS,
        ):
            bot.reply_to(message, "Для этой команды нужен доступ: /unlock_pro <код>.")
            return
    thinking_budget = tool_config.get("thinking_budget", None)

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
        if thinking_budget is not None:
            config_kwargs["thinking_config"] = genai_types.ThinkingConfig(
                thinking_budget=thinking_budget
            )

        if is_image_generation_model(model_to_use):
            config_kwargs["response_modalities"] = ["TEXT", "IMAGE"]

        response = generate_with_typing(
            chat_id,
            user_id, model_to_use, command, client.models.generate_content,
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
            send_rich_response(
                bot,
                chat_id,
                raw_response_text,
                reply_to_message_id=message.message_id,
            )

    except Exception as e:
        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass
        print(f"Error in quick tool command '{command}': {type(e).__name__}")
        bot.reply_to(
            message,
            f"Не удалось выполнить команду {command_with_slash}. {request_error_message(e)}",
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
                    print(f"Could not prepare pending file: {type(file_err).__name__}")
                    bot.send_message(
                        chat_id,
                        f"⚠️ Не удалось добавить файл '{file_info['filename']}' в запрос. Вложения сохранены.",
                    )
                    return

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

        response = generate_with_typing(
            chat_id,
            user_id, current_model, "chat", chat_session.send_message,
            message=api_message_parts, config=gemini_config
        )
        save_active_chat(user_id, clear_files=bool(files_in_context))
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
            send_rich_response(
                bot,
                message.chat.id,
                raw_response_text,
                reply_to_message_id=message.message_id,
                fallback_download_keyboard=get_file_download_keyboard(user_id),
            )
    except Exception as e:
        bot.reply_to(
            message,
            f"{request_error_message(e)}\n\nВозможно стоит "
            f"попробовать другую модель или начать новый чат.",
            reply_markup=get_main_keyboard(
                current_mode, search_enabled, current_model
            ),
        )


if __name__ == "__main__":
    db.init_db()
    # Recover from transport timeouts as well as Telegram API exceptions. Keep
    # update requests short so a stalled connection cannot hide fresh queries.
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5, allowed_updates=[
            'message', 'callback_query', 'inline_query', 'chosen_inline_result',
        ])
    finally:
        inline_panel.dispatcher.close()
        inline_panel.executor.shutdown(wait=False, cancel_futures=True)
