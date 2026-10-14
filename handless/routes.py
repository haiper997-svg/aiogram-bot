import asyncio
import logging
import json
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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        logging.info(f"📡 Статус ответа от сайта для {url}: {response.status_code}")

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            # 1. Поиск через JSON-LD (Schema.org микроразметка) — есть на Tilda, Bitrix и большинстве магазинов для SEO
            for script in soup.find_all("script", type="application/ld+json"):
                if script.string:
                    try:
                        data = json.loads(script.string)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if isinstance(item, dict):
                                offers = item.get("offers")
                                if offers:
                                    if isinstance(offers, list):
                                        offers = offers[0]
                                    price_val = offers.get("price") or offers.get("lowPrice")
                                    if price_val:
                                        clean = re.sub(r"\D", "", str(price_val))
                                        if clean:
                                            val = int(clean)
                                            if 50 <= val <= 1000000:
                                                logging.info(f"✅ Цена найдена через JSON-LD: {val}")
                                                return val
                                direct_price = item.get("price")
                                if direct_price:
                                    clean = re.sub(r"\D", "", str(direct_price))
                                    if clean:
                                        val = int(clean)
                                        if 50 <= val <= 1000000:
                                            logging.info(f"✅ Цена найдена через JSON-LD (direct): {val}")
                                            return val
                    except Exception:
                        pass

            # 2. Поиск в сыром HTML через JSON-шаблоны переменных (часто используется в Tilda и JS-приложениях)
            html_text = response.text
            price_matches = re.findall(r'"price"\s*:\s*["\']?(\d+)["\']?', html_text)
            for pm in price_matches:
                clean = re.sub(r"\D", "", pm)
                if clean:
                    val = int(clean)
                    if 50 <= val <= 1000000:
                        logging.info(f"✅ Цена найдена через JSON-шаблон в коде: {val}")
                        return val

            # 3. Поиск через стандартные мета-теги
            meta_tags = [
                {"property": "product:price:amount"},
                {"property": "og:price:amount"},
                {"itemprop": "price"}
            ]
            for tag_attr in meta_tags:
                meta = soup.find("meta", attrs=tag_attr) or soup.find(attrs=tag_attr)
                if meta:
                    val_str = meta.get("content") or meta.get("value")
                    if val_str:
                        clean = re.sub(r"\D", "", val_str)
                        if clean:
                            val = int(clean)
                            if 50 <= val <= 1000000:
                                logging.info(f"✅ Цена найдена через мета-тег: {val}")
                                return val

            # 4. Поиск по визуальным классам (Bitrix, Tilda)
            target_selectors = [
                {"class": "product-item-detail-price-current"},
                {"class": "product-item-price-current"},
                {"class": "js-product-price"},
                {"class": re.compile("price", re.I)},
                {"id": re.compile("price", re.I)}
            ]
            for selector in target_selectors:
                elements = soup.find_all(attrs=selector)
                for el in elements:
                    text = el.get_text(strip=True)
                    clean = re.sub(r"\D", "", text)
                    if clean:
                        val = int(clean)
                        if 50 <= val <= 1000000:
                            logging.info(f"✅ Цена найдена по селектору: {val}")
                            return val

        logging.warning(f"❌ Не удалось извлечь цену со страницы {url}")
        return None
    except Exception as e:
        logging.error(f"❌ Ошибка при запросе {url}: {e}")
        return None

async def notifier(bot: Bot):
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

        await asyncio.sleep(1800)

@router.message(Command('start'))
async def start(message: Message):
    await message.answer(
        "🤖 Бот мониторинга цен!\n\n"
        "Отправьте мне ссылку на товар в чат, и я начну следить за его ценой.\n\n"
        "Команды:\n"
        "/status — ваш товар и цена\n"
        "/stop — остановить отслеживание"
    )

@router.message(Command('status'))
async def status(message: Message):
    user_id = message.from_user.id
    if user_id in user_trackers:
        data = user_trackers[user_id]
        await message.answer(f"📋 Ваш товар:\n{data['url']}\n🏷 Цена: {data['last_price']} руб.")
    else:
        await message.answer("Нет активных отслеживаний.")

@router.message(Command('stop'))
async def stop(message: Message):
    user_id = message.from_user.id
    if user_id in user_trackers:
        del user_trackers[user_id]
        await message.answer("❌ Отслеживание остановлено.")
    else:
        await message.answer("У вас нет активных отслеживаний.")

@router.message(F.text.startswith("http"))
async def catch_product_link(message: Message):
    user_id = message.from_user.id
    url = message.text.strip()

    await message.answer("🔍 Проверяю ссылку...")
    initial_price = get_product_price(url)

    if initial_price is not None:
        user_trackers[user_id] = {"url": url, "last_price": initial_price}
        await message.answer(f"✅ Товар добавлен! Начальная цена: {initial_price} руб.")
    else:
        await message.answer("❌ Не удалось найти цену на странице.")
