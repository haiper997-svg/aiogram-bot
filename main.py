from os import getenv
import asyncio
from aiogram import Dispatcher, Bot
from handless.routes import router

TOKEN = getenv("BOT_TOKEN")

dp = Dispatcher()
dp.include_router(router)

async def main():
    bot = Bot(token=TOKEN)

    asyncio.create_task(notifier(bot))

    print("start...")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
