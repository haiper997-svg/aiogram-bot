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
