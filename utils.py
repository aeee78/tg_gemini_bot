import re

from bs4 import BeautifulSoup
from markdown import markdown

from constants import MAX_MESSAGE_LENGTH


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
