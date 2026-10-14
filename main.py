import asyncio
import logging
from os import getenv
from aiogram import Dispatcher, Bot, BaseMiddleware
from handless.routes import router, notifier

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана")


class LogUpdates(BaseMiddleware):
    async def __call__(self, handler, event, data):
        logging.info(f"📩 Входящее обновление: {event}")
        return await handler(event, data)


dp = Dispatcher()
dp.update.outer_middleware(LogUpdates())
dp.include_router(router)


async def main():
    logging.basicConfig(level=logging.DEBUG)
    bot = Bot(token=BOT_TOKEN)

    me = await bot.get_me()
    logging.info(f"✅ Бот: @{me.username}")

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("⏳ Тест: ОТПРАВЬТЕ БОТУ /start В БЛИЖАЙШИЕ 25 СЕКУНД")

    for i in range(1, 6):
        try:
            updates = await asyncio.wait_for(
                bot.get_updates(timeout=3, request_timeout=15), timeout=20
            )
            logging.info(f"🧪 getUpdates #{i}: получено {len(updates)} шт.")
        except Exception as e:
            logging.error(f"🧪 getUpdates #{i}: {type(e).__name__}: {e}")

    logging.info("Тест окончен, запускаю обычный polling")
    asyncio.create_task(notifier(bot))
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
