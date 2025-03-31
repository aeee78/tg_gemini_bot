from constants import IMAGE_COMMAND_PREFIXES, GEMINI_API_KEY
import base64
import io
import requests


def is_image_generation_request(text):
    """Проверяет, является ли запрос запросом на генерацию изображения."""
    text_lower = text.lower()
    return any(text_lower.startswith(prefix) for prefix in IMAGE_COMMAND_PREFIXES)


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
