from aiogram import Router, F, types
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.requests import get_or_create_user, get_file_contexts, add_file_context, add_to_buffer
from app.services.gemini import generate_response
from app.utils.text import split_long_message, markdown_to_text
from app.keyboards.builders import get_file_download_keyboard
from app.config import config

router = Router()

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: types.Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id)

    # Manual Mode Check
    if user.send_mode == config.SEND_MODE_MANUAL:
        await add_to_buffer(session, user.telegram_id, "text", message.text)
        await message.reply("📝 Добавлено в буфер. Нажмите 'Отправить всё' для отправки.")
        return

    # Immediate Mode
    wait_msg = await message.answer("⏳ Думаю...")
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        # Load Context Files (files uploaded previously in this session)
        context_files_data = []
        db_files = await get_file_contexts(session, user.telegram_id)

        if db_files:
            await message.bot.send_chat_action(message.chat.id, "upload_document")
            # Limit number of files to prevent timeout
            for f_db in db_files[:10]:
                try:
                    f_info = await message.bot.get_file(f_db.file_id)
                    f_io = await message.bot.download_file(f_info.file_path)
                    data = f_io.read()
                    context_files_data.append({
                        'data': data,
                        'mime_type': f_db.mime_type,
                        'caption': f_db.caption,
                        'filename': f_db.file_name
                    })
                except Exception as e:
                    print(f"Failed to download context file {f_db.file_name}: {e}")

        text_resp, images = await generate_response(
            session,
            user.telegram_id,
            message.text,
            files_data=context_files_data, # Pass downloaded files
            use_search=user.search_enabled,
            model=user.current_model
        )

        await wait_msg.delete()

        # Send Images (if generated)
        if images:
            for img in images:
                file = BufferedInputFile(img['data'], filename="image.png")
                await message.answer_photo(file)

        # Send Text
        if text_resp:
            clean_text = markdown_to_text(text_resp)
            parts = split_long_message(clean_text)

            for i, part in enumerate(parts):
                reply_to = message.message_id if i == 0 else None
                await message.answer(part, reply_to_message_id=reply_to)

            if len(parts) > 1:
                await message.answer("Ответ был длинным и разбит на части.",
                                     reply_markup=get_file_download_keyboard(user.telegram_id))

    except Exception as e:
        try:
            await wait_msg.delete()
        except:
            pass
        await message.reply(f"❌ Ошибка: {str(e)}")

# File Handling (Photos/Docs)
@router.message(F.photo | F.document)
async def handle_file(message: types.Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id)

    # Identify file
    file_id = None
    file_name = "file"
    mime_type = "application/octet-stream"

    if message.photo:
        file_id = message.photo[-1].file_id
        file_name = "photo.jpg"
        mime_type = "image/jpeg"
    elif message.document:
        if message.document.mime_type not in config.SUPPORTED_MIME_TYPES:
             if user.send_mode == config.SEND_MODE_MANUAL:
                 # In manual mode we allow it to buffer? No, better stick to supported.
                 pass
             else:
                 await message.reply("⚠️ Этот тип файла не поддерживается.")
                 return
        file_id = message.document.file_id
        file_name = message.document.file_name
        mime_type = message.document.mime_type

    caption = message.caption or ""

    if user.send_mode == config.SEND_MODE_MANUAL:
        await add_to_buffer(session, user.telegram_id,
                            "photo" if message.photo else "document",
                            file_id,
                            caption=caption,
                            mime_type=mime_type,
                            file_name=file_name)
        await message.reply("📎 Файл добавлен в буфер.")
    else:
        # Immediate Mode

        if message.document:
            # Documents -> Add to Context (to be used in next text query)
            await add_file_context(session, user.telegram_id, file_id, file_name, mime_type, caption)
            await message.reply(f"📄 Файл '{file_name}' добавлен в контекст. Он будет использован в следующем запросе.")

        elif message.photo:
            # Photos -> Immediate Analysis
            wait_msg = await message.answer("👀 Смотрю...")
            await message.bot.send_chat_action(message.chat.id, "upload_photo")

            try:
                # Download for immediate analysis
                file_info = await message.bot.get_file(file_id)
                file_bytes_io = await message.bot.download_file(file_info.file_path)
                file_data = file_bytes_io.read()

                current_file_data = [{
                    'data': file_data,
                    'mime_type': mime_type,
                    'caption': caption,
                    'filename': file_name
                }]

                text_resp, images = await generate_response(
                    session,
                    user.telegram_id,
                    caption if caption else "Describe this image",
                    files_data=current_file_data,
                    model=user.current_model
                )

                await wait_msg.delete()

                clean_text = markdown_to_text(text_resp)
                parts = split_long_message(clean_text)
                for part in parts:
                    await message.answer(part)

            except Exception as e:
                try:
                    await wait_msg.delete()
                except:
                    pass
                await message.reply(f"❌ Ошибка: {e}")
