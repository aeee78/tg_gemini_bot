import json
import base64

from bs4 import BeautifulSoup
from markdown import markdown
from telebot.types import InputRichMessage, ReplyParameters

from constants import MAX_MESSAGE_LENGTH


class BytesEncoder(json.JSONEncoder):
    """Custom JSON Encoder that converts bytes to base64 strings."""

    def default(self, obj):
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("utf-8")
        return super().default(obj)


def markdown_to_text(markdown_string):
    """Converts a markdown string to plaintext"""
    html = markdown(markdown_string)
    soup = BeautifulSoup(html, "html.parser")

    # Replace <br> tags with explicit newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Add newlines after block elements to ensure separation
    block_tags = [
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "hr",
        "div",
        "table",
        "tr",
    ]
    for tag in soup.find_all(block_tags):
        tag.append("\n")

    # Add spaces after table cells to ensure separation
    for tag in soup.find_all(["td", "th"]):
        tag.append(" ")

    text = soup.get_text(separator="")

    return text.strip()


def parse_markdown_state(text: str) -> dict:
    """
    Анализирует текст и определяет, какие Markdown-теги остались открытыми:
    - fenced code block (```lang)
    - inline code (`)
    - bold (**)
    - italic (*)
    - strikethrough (~~)
    - spoiler (||)
    """
    in_code_block = False
    code_block_lang = ""
    in_inline_code = False
    in_bold = False
    in_italic = False
    in_strike = False
    in_spoiler = False

    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_block_lang = stripped[3:].strip()
            else:
                in_code_block = False
                code_block_lang = ""
            continue

        if in_code_block:
            continue

        i = 0
        n = len(line)
        while i < n:
            if line[i] == "`":
                in_inline_code = not in_inline_code
                i += 1
            elif in_inline_code:
                i += 1
            elif line[i : i + 2] == "||":
                in_spoiler = not in_spoiler
                i += 2
            elif line[i : i + 2] == "~~":
                in_strike = not in_strike
                i += 2
            elif line[i : i + 3] == "***":
                in_bold = not in_bold
                in_italic = not in_italic
                i += 3
            elif line[i : i + 2] == "**":
                in_bold = not in_bold
                i += 2
            elif line[i] == "*":
                # Не считаем маркированный список (* в начале строки с пробелом) за курсив
                if i == 0 and len(line) > 1 and line[1] == " ":
                    i += 1
                else:
                    in_italic = not in_italic
                    i += 1
            else:
                i += 1

    return {
        "in_code_block": in_code_block,
        "code_block_lang": code_block_lang,
        "in_inline_code": in_inline_code,
        "in_bold": in_bold,
        "in_italic": in_italic,
        "in_strike": in_strike,
        "in_spoiler": in_spoiler,
    }


def get_closers_and_openers(state: dict) -> tuple[str, str]:
    """
    Возвращает суффикс для закрытия открытых тегов в текущей части
    и префикс для повторного открытия их в следующей части.
    """
    suffix = []
    prefix = []

    if state["in_bold"]:
        suffix.append("**")
        prefix.append("**")
    if state["in_italic"]:
        suffix.append("*")
        prefix.append("*")
    if state["in_strike"]:
        suffix.append("~~")
        prefix.append("~~")
    if state["in_spoiler"]:
        suffix.append("||")
        prefix.append("||")
    if state["in_inline_code"]:
        suffix.append("`")
        prefix.append("`")
    if state["in_code_block"]:
        suffix.append("\n```")
        lang = state["code_block_lang"]
        prefix.insert(0, f"```{lang}\n" if lang else "```\n")

    return "".join(suffix), "".join(prefix)


def split_long_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """
    Умно разбивает длинный Markdown текст на части, автоматически
    закрывая и заново открывая открытые теги форматирования (код, жирный, курсив и т.д.)
    на границах сообщений.
    """
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    parts = []
    current_text = text
    current_prefix = ""

    while current_text:
        if len(current_text) + len(current_prefix) <= max_length:
            parts.append(current_prefix + current_text)
            break

        # Учитываем запас под закрывающие теги (например, **\n```)
        safety_reserve = min(50, max(0, max_length // 4))
        available_len = max(1, max_length - len(current_prefix) - safety_reserve)

        candidate_chunk = current_text[:available_len]

        cut_idx = -1
        delimiter_len = 0

        # 1. Двойной перенос строки (между параграфами / таблицами)
        pos = candidate_chunk.rfind("\n\n")
        if pos != -1 and pos > available_len // 4:
            cut_idx = pos
            delimiter_len = 2

        # 2. Одинарный перенос строки
        if cut_idx == -1:
            pos = candidate_chunk.rfind("\n")
            if pos != -1 and pos > available_len // 4:
                cut_idx = pos
                delimiter_len = 1

        # 3. Конец предложения
        if cut_idx == -1:
            for punct in (". ", "! ", "? "):
                pos = candidate_chunk.rfind(punct)
                if pos != -1 and pos > available_len // 4:
                    cut_idx = pos + 1
                    delimiter_len = 1
                    break

        # 4. Пробел
        if cut_idx == -1:
            pos = candidate_chunk.rfind(" ")
            if pos != -1:
                cut_idx = pos
                delimiter_len = 1

        # 5. Принудительный разрыв
        if cut_idx == -1:
            cut_idx = available_len
            delimiter_len = 0

        raw_chunk = current_text[:cut_idx]
        current_text = current_text[cut_idx + delimiter_len :].lstrip("\n")

        # Определяем открытые теги в этой части
        combined_chunk = current_prefix + raw_chunk
        state = parse_markdown_state(combined_chunk)
        suffix, next_prefix = get_closers_and_openers(state)

        final_part = combined_chunk + suffix
        parts.append(final_part)
        current_prefix = next_prefix

    return parts


def send_rich_response(
    bot,
    chat_id,
    markdown_text,
    reply_to_message_id=None,
    reply_markup=None,
    fallback_download_keyboard=None,
):
    """
    Отправляет форматированный ответ в чат с использованием Telegram Bot API Rich Messages
    (лимит до 32 768 символов, нативные таблицы, заголовки, списки, формулы).
    В случае ошибки Telegram API автоматически делает fallback на обычные текстовые сообщения.
    """
    if not markdown_text:
        return []

    parts = split_long_message(markdown_text, max_length=MAX_MESSAGE_LENGTH)
    sent_messages = []
    total_parts_sent = 0

    for i, part in enumerate(parts):
        is_first = i == 0
        is_last = i == len(parts) - 1
        reply_params = (
            ReplyParameters(message_id=reply_to_message_id)
            if (is_first and reply_to_message_id)
            else None
        )
        current_markup = reply_markup if is_last else None

        try:
            rich_msg = InputRichMessage(markdown=part)
            msg = bot.send_rich_message(
                chat_id=chat_id,
                rich_message=rich_msg,
                reply_parameters=reply_params,
                reply_markup=current_markup,
            )
            sent_messages.append(msg)
            total_parts_sent += 1
        except Exception:
            # Fallback: конвертируем в простой текст и делим на части по 4000 символов
            plain_part = markdown_to_text(part)
            fallback_chunks = split_long_message(plain_part, max_length=4000)
            for j, chunk in enumerate(fallback_chunks):
                chunk_reply_params = (
                    reply_params if (is_first and j == 0) else None
                )
                chunk_markup = (
                    current_markup
                    if (is_last and j == len(fallback_chunks) - 1)
                    else None
                )
                msg = bot.send_message(
                    chat_id,
                    chunk,
                    reply_parameters=chunk_reply_params,
                    reply_markup=chunk_markup,
                )
                sent_messages.append(msg)
                total_parts_sent += 1

    if total_parts_sent > 1 and fallback_download_keyboard:
        bot.send_message(
            chat_id,
            "Ответ был разбит на несколько сообщений.",
            reply_markup=fallback_download_keyboard,
        )

    return sent_messages

