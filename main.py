import asyncio
import logging
from aiogram import Dispatcher, Bot
from handless.routes import router, notifier

dp = Dispatcher()
dp.include_router(router)

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)

    asyncio.create_task(notifier(bot))

    print("start...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
