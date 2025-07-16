import re

from bs4 import BeautifulSoup
from markdown import markdown

from constants import MAX_MESSAGE_LENGTH


def markdown_to_text(markdown_string):
    """Converts a markdown string to plaintext"""
    html = markdown(markdown_string)
    soup = BeautifulSoup(html, "html.parser")
    text = "".join(soup.findAll(text=True))

    return text


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
