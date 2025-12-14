from typing import Callable, Awaitable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async for session in self.session_factory():
            data["session"] = session
            try:
                return await handler(event, data)
            finally:
                # Session closes automatically due to context manager in generator
                pass
