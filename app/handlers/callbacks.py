from aiogram import Router, F, types
from app.utils.text import markdown_to_text
from app.database.requests import get_chat_history
from aiogram.types import BufferedInputFile

router = Router()

@router.callback_query(F.data.startswith("get_file_") | F.data.startswith("get_md_"))
async def download_response(callback: types.CallbackQuery, session):
    # Retrieve last response?
    # Original bot stored `user_last_responses[user_id]`.
    # We don't have that in memory. We have DB history.
    # We can get the LAST message with role='model' for this user.

    from app.database.requests import get_chat_history
    history = await get_chat_history(session, callback.from_user.id)

    # Filter for model messages, get last
    model_msgs = [m for m in history if m.role == 'model']
    if not model_msgs:
        await callback.answer("Нет истории.", show_alert=True)
        return

    last_msg = model_msgs[-1]
    raw_content = last_msg.content

    is_txt = callback.data.startswith("get_file_")

    if is_txt:
        content = markdown_to_text(raw_content)
        ext = "txt"
    else:
        content = raw_content
        ext = "md"

    f = BufferedInputFile(content.encode(), filename=f"response.{ext}")
    await callback.message.answer_document(f)
    await callback.answer()
