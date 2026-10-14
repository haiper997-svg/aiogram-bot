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

background_tasks = set()


async def handle_update(bot: Bot, update):
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logging.exception("Ошибка при обработке обновления")


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)

    me = await bot.get_me()
    logging.info(f"✅ Бот: @{me.username}")

    await bot.delete_webhook()  # сообщения в очереди не сбрасываем

    asyncio.create_task(notifier(bot))

    print("start... (ручной polling)")
    offset = None
    while True:
        try:
            updates = await bot.get_updates(
                offset=offset, timeout=30, request_timeout=40
            )
        except Exception as e:
            logging.error(f"getUpdates: {type(e).__name__}: {e}")
            await asyncio.sleep(3)
            continue

        for update in updates:
            offset = update.update_id + 1
            task = asyncio.create_task(handle_update(bot, update))
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)


if __name__ == '__main__':
    asyncio.run(main())
