from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from app.services.gemini import quick_tool_call
from app.utils.text import split_long_message, markdown_to_text
from app.config import config
from app.services.tools_config import QUICK_TOOLS_CONFIG

router = Router()

@router.message(F.text.startswith("/"))
async def handle_quick_tool(message: types.Message, command: CommandObject):
    # This handler catches ALL commands, so we must filter for tools
    cmd_name = command.command

    if cmd_name not in QUICK_TOOLS_CONFIG:
        return # Not a tool, let other handlers process it (e.g. /start)

    tool_config = QUICK_TOOLS_CONFIG[cmd_name]

    user_query = command.args
    if not user_query:
        await message.reply(f"❗ Введите текст для команды /{cmd_name}")
        return

    wait_msg = await message.answer(f"🛠 Выполняю {cmd_name}...")

    resp_text = await quick_tool_call(cmd_name, user_query, tool_config)

    await wait_msg.delete()

    clean_text = markdown_to_text(resp_text)

    parts = split_long_message(clean_text)
    for part in parts:
        await message.answer(part)

    if cmd_name in ["todo", "markdown", "dayplanner"]:
        from aiogram.types import BufferedInputFile
        f = BufferedInputFile(resp_text.encode(), filename=f"{cmd_name}.md")
        await message.answer_document(f, caption="📄 Исходный Markdown")
