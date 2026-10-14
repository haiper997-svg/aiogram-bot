import asyncio
import logging
from aiogram import Dispatcher, Bot
from handless.routes import router, notifier

dp = Dispatcher()
dp.include_router(router)

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)

    asyncio.create_task(notifier(bot))

    print("start...")
    await dp.start_polling(bot)

if name == 'main':
    asyncio.run(main())
