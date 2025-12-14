from aiogram import Router, F, types
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.requests import get_or_create_user, get_buffer, clear_buffer
from app.services.gemini import generate_response
from app.utils.text import split_long_message, markdown_to_text
from app.config import config

router = Router()

@router.message(F.text == "Отправить всё")
async def send_all_buffer(message: types.Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id)

    if user.send_mode != config.SEND_MODE_MANUAL:
        await message.reply("⚠️ Вы не в ручном режиме.")
        return

    buffer_items = await get_buffer(session, user.telegram_id)

    if not buffer_items:
        await message.reply("📭 Буфер пуст.")
        return

    wait_msg = await message.answer("📤 Отправляю накопленное...")
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Construct combined prompt
    combined_text = ""
    files_data = []

    for item in buffer_items:
        if item.item_type == 'text':
            if combined_text:
                combined_text += "\n\n"
            combined_text += item.content
        elif item.item_type in ['photo', 'document']:
            # We stored file_id in content
            file_id = item.content
            try:
                # Download file
                file_info = await message.bot.get_file(file_id)
                f_io = await message.bot.download_file(file_info.file_path)
                data = f_io.read()

                files_data.append({
                    'data': data,
                    'mime_type': item.mime_type,
                    'caption': item.caption,
                    'filename': item.file_name
                })

                if item.caption:
                     if combined_text: combined_text += "\n"
                     combined_text += f"[Caption: {item.caption}]"

            except Exception as e:
                combined_text += f"\n[Ошибка загрузки файла из буфера: {e}]"

    try:
        text_resp, images = await generate_response(
            session,
            user.telegram_id,
            combined_text if combined_text else "Проанализируй эти файлы.",
            files_data=files_data,
            use_search=user.search_enabled,
            model=user.current_model
        )

        await clear_buffer(session, user.telegram_id)
        await wait_msg.delete()

        if images:
            for img in images:
                 file = BufferedInputFile(img['data'], filename="gen.png")
                 await message.answer_photo(file)

        if text_resp:
            clean = markdown_to_text(text_resp)
            parts = split_long_message(clean)
            for part in parts:
                await message.answer(part)

    except Exception as e:
        await wait_msg.delete()
        await message.reply(f"❌ Ошибка отправки буфера: {e}")
