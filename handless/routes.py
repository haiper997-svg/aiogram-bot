import asyncio

import logging
import re
import requests
from bs4 import BeautifulSoup

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import Bot

router = Router()

user_trackers = {}

def get_product_price(url: str) -> int | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            # ⚠️ Универсальный поиск цены.
            # Для конкретного магазина (например, Torch Shop) возможно придется уточнить класс,
            # например: soup.find("span", class_="price-val")
            price_element = soup.find("span", class_="price") or soup.find("div", class_="price")

            if price_element:
                clean_price = re.sub(r"\D", "", price_element.text)
                return int(clean_price) if clean_price else None
        return None
    except Exception as e:
        logging.error(f"Ошибка при парсинге {url}: {e}")
        return None

async def price_checker_loop(bot: Bot):
    while True:
        if user_trackers:
            for user_id, data in list(user_trackers.items()):
                url = data["url"]
                last_price = data["last_price"]

                current_price = get_product_price(url)

                if current_price is not None:
                    if last_price is None:
                        user_trackers[user_id]["last_price"] = current_price

                    elif current_price != last_price:
                        if current_price < last_price:
                            diff = last_price - current_price
                            text = (
                                f"🔥 Цена снизилась!\n\n"
                                f"🔗 [Ссылка на товар]({url})\n"
                                f"📉 Было: {last_price} руб.\n"
                                f"📈 Стало: {current_price} руб.\n"
                                f"💰 Экономия: {diff} руб."
                            )
                        else:
                            diff = current_price - last_price
                            text = (
                                f"📈 Цена выросла!\n\n"
                                f"🔗 [Ссылка на товар]({url})\n"
                                f"📉 Было: {last_price} руб.\n"
                                f"📈 Стало: {current_price} руб.\n"
                                f"⚠️ Рост на: {diff} руб."
                            )

                        try:
                            await bot.send_message(user_id, text, parse_mode="Markdown")
                        except Exception:
                            pass

                        user_trackers[user_id]["last_price"] = current_price

        await asyncio.sleep(3600)
        
        if subscribers:
            for user_id in list(subscribers):
                try:
                    await bot.send_message(user_id, "Заплатите 300р чтобы продолжить")
                except Exception:
                    pass

        await asyncio.sleep(5)

@router.message(Command('start'))
async def start(message: Message):
    await message.answer(
        "🤖 Бот мониторинга цен!\n\n"
        "Просто отправьте мне ссылку на товар в чат, и я начну следить за его ценой.\n\n"
        "Команды:\n"
        "/status — посмотреть, какой товар вы сейчас отслеживаете\n"
        "/stop — удалить товар из отслеживания"
    )

@router.message(Command('status'))
async def status(message: Message):
    user_id = message.from_user.id
    if user_id in user_trackers:
        data = user_trackers[user_id]
        await message.answer(
            f"📋 Ваш товар:\n{data['url']}\n"
            f"🏷 Последняя известная цена: {data['last_price']} руб."
        )
    else:
        await message.answer("Вы еще не отправили ни одной ссылки для отслеживания.")

@router.message(Command('stop'))
async def stop(message: Message):
    user_id = message.from_user.id
    if user_id in user_trackers:
        del user_trackers[user_id]
        await message.answer("❌ Отслеживание остановлено, товар удален.")
    else:
        await message.answer("У вас нет активных отслеживаний.")

@router.message(F.text.startswith("http"))
async def catch_product_link(message: Message):
    user_id = message.from_user.id
    url = message.text.strip()

    await message.answer("🔍 Проверяю ссылку и определяю цену товара...")

    initial_price = get_product_price(url)

    if initial_price is not None:
        user_trackers[user_id] = {
            "url": url,
            "last_price": initial_price
        }
        await message.answer(
            f"✅ Товар успешно добавлен!\n\n"
            f"Начальная цена: {initial_price} руб.\n"
            f"Я буду проверять её и пришлю уведомление, если она упадет."
        )
    else:
        await message.answer(
            "❌ Не удалось найти цену на этой странице.\n"
            "Убедитесь, что скинули прямую ссылку на товар, а не на главную страницу каталога."
        )
