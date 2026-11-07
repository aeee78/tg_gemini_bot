"""Serialize and carry conversation content between Gemini models."""
import io
import json

from google.genai import types
from PIL import Image

from utils import BytesEncoder


def serialize_history(history):
    return json.dumps([content.model_dump() for content in history], cls=BytesEncoder)


def portable_history(history):
    """Keep dialogue and media, excluding model-specific reasoning data."""
    result = []
    for content in history:
        parts = [part.model_copy(deep=True, update={'thought_signature': None, 'thought': None})
                 for part in (content.parts or []) if not part.thought]
        if parts:
            result.append(content.model_copy(deep=True, update={'parts': parts}))
    return result


def context_contents(history, files, buffer):
    """Build a countable snapshot of history and pending user content."""
    contents = list(history)
    parts = []
    for entry in files:
        if entry.get('caption'):
            parts.append(types.Part.from_text(text=entry['caption']))
        parts.append(types.Part.from_bytes(mime_type=entry['mime_type'], data=entry['data']))
        parts.append(types.Part.from_text(text=f"(Файл: {entry['filename']})"))
    for entry in buffer:
        text = entry.get('content') if entry['type'] == 'text' else entry.get('caption')
        if text:
            parts.append(types.Part.from_text(text=text))
        if entry['type'] == 'photo' and entry.get('image') is not None:
            image = entry['image']
            stream = io.BytesIO()
            image.save(stream, format=image.format or 'PNG')
            parts.append(types.Part.from_bytes(data=stream.getvalue(), mime_type=Image.MIME.get(image.format or 'PNG', 'image/png')))
        elif entry['type'] == 'voice':
            parts.append(types.Part.from_bytes(data=entry['data'], mime_type=entry['mime_type']))
        elif entry['type'] == 'document':
            parts.append(types.Part.from_bytes(data=entry['data'], mime_type=entry['mime_type']))
            parts.append(types.Part.from_text(text=f"(Файл: {entry['filename']})"))
    if parts:
        contents.append(types.Content(role='user', parts=parts))
    return contents
