import io
from google import genai
from google.genai import types as genai_types
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from app.config import config
from app.database.requests import get_chat_history, add_message, get_file_contexts
from app.utils.text import markdown_to_text
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

client = genai.Client(api_key=config.GEMINI_API_KEY)

async def generate_response(
    session: AsyncSession,
    telegram_id: int,
    user_prompt: str,
    files_data: list = None,
    use_search: bool = False,
    model: str = None
):
    """
    Core function to generate response.
    1. Reconstruct history from DB.
    2. Add context files.
    3. Call Gemini.
    4. Save response to DB.
    """

    if not model:
        model = config.DEFAULT_MODEL

    # 1. Fetch History
    history_rows = await get_chat_history(session, telegram_id)

    is_img_gen = (model == "gemini-2.5-flash-image-preview")

    chat_history = []
    if not is_img_gen:
        for row in history_rows:
            parts = [genai_types.Part.from_text(text=row.content)]
            chat_history.append(
                genai_types.Content(
                    role=row.role,
                    parts=parts
                )
            )

    # 3. Prepare Current Message (Prompt + Files)
    message_parts = []

    # files_data contains both current files AND context files (downloaded by handler)
    if files_data:
        for file_item in files_data:
            if file_item.get('caption'):
                message_parts.append(file_item['caption'])

            try:
                message_parts.append(
                    genai_types.Part.from_bytes(
                        mime_type=file_item['mime_type'],
                        data=file_item['data']
                    )
                )
                if file_item.get('filename'):
                    message_parts.append(f"(Файл: {file_item['filename']})")
            except Exception as e:
                print(f"Error attaching file: {e}")

    message_parts.append(user_prompt)

    # 4. Configure & Call
    def call_gemini():
        tools = []
        if use_search and not is_img_gen:
             tools.append(Tool(google_search=GoogleSearch()))

        config_args = {}
        if tools:
            config_args['tools'] = tools

        if is_img_gen:
            config_args['response_modalities'] = ["TEXT", "IMAGE"]

        chat = client.chats.create(
            model=model,
            history=chat_history if not is_img_gen else []
        )

        response = chat.send_message(
            message=message_parts,
            config=GenerateContentConfig(**config_args)
        )
        return response

    try:
        response = await asyncio.to_thread(call_gemini)
    except Exception as e:
        return f"Ошибка API Gemini: {str(e)}", []

    # 5. Process Response
    text_content = ""
    images_data = []

    if hasattr(response, "candidates") and response.candidates:
        for candidate in response.candidates:
            if hasattr(candidate, "content") and candidate.content:
                 if hasattr(candidate.content, "parts") and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_content += part.text
                        elif hasattr(part, "inline_data"):
                            images_data.append({
                                'mime_type': part.inline_data.mime_type,
                                'data': part.inline_data.data
                            })

    if not text_content and hasattr(response, "text") and response.text:
        text_content = response.text

    # Extract Sources
    try:
        if (response.candidates and
            response.candidates[0].grounding_metadata and
            response.candidates[0].grounding_metadata.grounding_chunks):

            sources = []
            for i, chunk in enumerate(response.candidates[0].grounding_metadata.grounding_chunks):
                if hasattr(chunk, "web") and chunk.web.uri:
                     title = chunk.web.title if chunk.web.title else chunk.web.uri
                     sources.append(f"{i + 1}. [{title}]({chunk.web.uri})")

            if sources:
                text_content += "\n\nИсточники:\n" + "\n".join(sources)
    except Exception:
        pass

    # 6. Save to DB
    await add_message(session, telegram_id, 'user', user_prompt, has_images=bool(files_data))
    await add_message(session, telegram_id, 'model', text_content, has_images=bool(images_data))

    return text_content, images_data

async def quick_tool_call(command: str, user_query: str, tool_config: dict):
    """
    Handles single-shot commands like /translate, /rewrite
    """
    import asyncio

    system_instruction = tool_config["system_instruction"]
    model_to_use = tool_config.get("model", config.DEFAULT_MODEL)
    thinking_budget = tool_config.get("thinking_budget", None)

    def call():
        config_kwargs = {"system_instruction": system_instruction}

        if model_to_use == "gemini-2.5-flash" and thinking_budget is not None:
             config_kwargs["thinking_config"] = genai_types.ThinkingConfig(
                thinking_budget=thinking_budget
            )

        response = client.models.generate_content(
            model=model_to_use,
            contents=user_query,
            config=genai_types.GenerateContentConfig(**config_kwargs)
        )
        return response

    try:
        response = await asyncio.to_thread(call)
        return response.text
    except Exception as e:
        return f"Error: {e}"
