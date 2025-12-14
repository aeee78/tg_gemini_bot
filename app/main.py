import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.config import config
from app.database.core import init_db, get_session
from app.handlers import base, settings, chat, manual, tools, callbacks
from app.middlewares.db_middleware import DbSessionMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)

async def main():
    # Initialize Database
    await init_db()

    # Initialize Bot and Dispatcher
    bot = Bot(token=config.TELEGRAM_TOKEN)
    dp = Dispatcher()

    # Middleware
    dp.update.middleware(DbSessionMiddleware(get_session))

    # Register Routers
    # Order matters!
    dp.include_router(base.router)
    dp.include_router(settings.router)
    dp.include_router(manual.router)
    dp.include_router(tools.router)
    dp.include_router(callbacks.router)
    dp.include_router(chat.router) # Catch-all text handler last

    # Start polling
    print("Bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")
