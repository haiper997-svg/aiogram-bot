import asyncio
import logging
from os import getenv
from aiogram import Dispatcher, Bot
from handless.routes import router, notifier

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌Ошибка")

dp = Dispatcher()
dp.include_router(router)

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)

    asyncio.create_task(notifier(bot))

    print("start...")
    await dp.start_polling(bot)

if name == 'main':
    asyncio.run(main())

