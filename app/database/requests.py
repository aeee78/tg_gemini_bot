from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, Message, FileContext, BufferItem
from app.config import config

async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).filter(User.telegram_id == telegram_id))
    user = result.scalars().first()

    if not user:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user

async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).filter(User.telegram_id == telegram_id))
    return result.scalars().first()

async def update_user_model(session: AsyncSession, telegram_id: int, model: str):
    user = await get_or_create_user(session, telegram_id)
    user.current_model = model
    await session.commit()

async def update_user_mode(session: AsyncSession, telegram_id: int, mode: str):
    user = await get_or_create_user(session, telegram_id)
    user.send_mode = mode
    await session.commit()

async def toggle_search(session: AsyncSession, telegram_id: int):
    user = await get_or_create_user(session, telegram_id)
    user.search_enabled = not user.search_enabled
    await session.commit()
    return user.search_enabled

async def set_whitelist(session: AsyncSession, telegram_id: int, status: bool = True):
    user = await get_or_create_user(session, telegram_id)
    user.is_whitelisted = status
    await session.commit()

async def add_message(session: AsyncSession, telegram_id: int, role: str, content: str, has_images: bool = False):
    user = await get_or_create_user(session, telegram_id)
    message = Message(user_id=user.id, role=role, content=content, has_images=has_images)
    session.add(message)
    await session.commit()

async def get_chat_history(session: AsyncSession, telegram_id: int, limit: int = 50):
    user = await get_or_create_user(session, telegram_id)
    # Order by timestamp asc to reconstruct history
    result = await session.execute(
        select(Message).filter(Message.user_id == user.id).order_by(Message.timestamp.asc())
        # .limit(limit) # Logic might need to be smarter about limit vs full context
    )
    return result.scalars().all()

async def clear_history(session: AsyncSession, telegram_id: int):
    user = await get_or_create_user(session, telegram_id)
    await session.execute(delete(Message).filter(Message.user_id == user.id))
    await session.execute(delete(FileContext).filter(FileContext.user_id == user.id))
    # Note: Buffer is usually separate from chat history context, but maybe clear it too?
    # Let's keep buffer separate as it is "draft" area.
    await session.commit()

async def add_file_context(session: AsyncSession, telegram_id: int, file_id: str, file_name: str, mime_type: str, caption: str = None):
    user = await get_or_create_user(session, telegram_id)
    file_ctx = FileContext(
        user_id=user.id,
        file_id=file_id,
        file_name=file_name,
        mime_type=mime_type,
        caption=caption
    )
    session.add(file_ctx)
    await session.commit()

async def get_file_contexts(session: AsyncSession, telegram_id: int):
    user = await get_or_create_user(session, telegram_id)
    result = await session.execute(select(FileContext).filter(FileContext.user_id == user.id))
    return result.scalars().all()

# Buffer Operations
async def add_to_buffer(session: AsyncSession, telegram_id: int, item_type: str, content: str, caption: str = None, mime_type: str = None, file_name: str = None):
    user = await get_or_create_user(session, telegram_id)
    item = BufferItem(
        user_id=user.id,
        item_type=item_type,
        content=content,
        caption=caption,
        mime_type=mime_type,
        file_name=file_name
    )
    session.add(item)
    await session.commit()

async def get_buffer(session: AsyncSession, telegram_id: int):
    user = await get_or_create_user(session, telegram_id)
    result = await session.execute(select(BufferItem).filter(BufferItem.user_id == user.id).order_by(BufferItem.timestamp.asc()))
    return result.scalars().all()

async def clear_buffer(session: AsyncSession, telegram_id: int):
    user = await get_or_create_user(session, telegram_id)
    await session.execute(delete(BufferItem).filter(BufferItem.user_id == user.id))
    await session.commit()
