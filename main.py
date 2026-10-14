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
    logging.basicConfig(level=logging.DEBUG)
    bot = Bot(token=BOT_TOKEN)

    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=20)
        logging.info(f"✅ Telegram доступен, бот: @{me.username}")
    except asyncio.TimeoutError:
        logging.error("❌ Нет ответа от api.telegram.org за 20 секунд (сеть хостинга или блокировка)")
        return
    except Exception as e:
        logging.error(f"❌ Ошибка get_me: {type(e).__name__}: {e}")
        return

    asyncio.create_task(notifier(bot))

    print("start...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

