import asyncio
import logging
import json
import re
import requests
from bs4 import BeautifulSoup
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

user_trackers = {}

MIN_PRICE = 50
MAX_PRICE = 1_000_000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Число с пробелами-разделителями тысяч и необязательными копейками
NUM_RE = re.compile(
    r"\d{1,3}(?:[\s\u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
)


def fetch_page(url: str) -> requests.Response:
    """Загружает страницу, проходя cookie-заглушку хостинга Beget."""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.set("beget", "begetok")  # cookie, которую ставит заглушка

    response = session.get(url, timeout=15)

    # Если заглушка всё равно пришла, повторяем запрос уже с cookie
    if "beget=begetok" in response.text and len(response.text) < 2000:
        response = session.get(url, timeout=15)

    return response


def parse_price(raw) -> int | None:
    """Достаёт ПЕРВОЕ число из строки и проверяет диапазон. Копейки отбрасываются."""
    if raw is None:
        return None
    m = NUM_RE.search(str(raw))
    if not m:
        return None
    num = re.sub(r"[\s\u00a0\u202f]", "", m.group()).replace(",", ".")
    try:
        val = int(float(num))
    except ValueError:
        return None
    return val if MIN_PRICE <= val <= MAX_PRICE else None


def _walk_offers(node):
    """Рекурсивно ищет в JSON-LD блоки offers и возвращает цены."""
    if isinstance(node, dict):
        if "offers" in node:
            yield from _walk_offers(node["offers"])
        for key in ("price", "lowPrice"):
            if key in node:
                yield node[key]
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from _walk_offers(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_offers(item)


def extract_structured_price(soup: BeautifulSoup) -> int | None:
    # 1. microdata: <meta itemprop="price" content="1299.00">
    for el in soup.find_all(attrs={"itemprop": "price"}):
        val = parse_price(el.get("content") or el.get_text())
        if val:
            return val

    # 2. Open Graph
    for prop in ("product:price:amount", "og:price:amount"):
        meta = soup.find("meta", attrs={"property": prop})
        if meta:
            val = parse_price(meta.get("content"))
            if val:
                return val

    # 3. JSON-LD
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except Exception:
            continue
        for raw in _walk_offers(data):
            val = parse_price(raw)
            if val:
                return val
    return None


def extract_selector_price(soup: BeautifulSoup) -> int | None:
    # Bitrix: точные селекторы
    for el in soup.select(".product-item-detail-price-current, [id$='_price']"):
        val = parse_price(el.get_text(" ", strip=True))
        if val:
            return val

    # Любой элемент с "price" в классе: проверяем КАЖДЫЙ, а не только первый
    for el in soup.find_all(class_=re.compile("price", re.I)):
        classes = " ".join(el.get("class", [])).lower()
        if "old" in classes:  # старая цена
            continue
        val = parse_price(el.get_text(" ", strip=True))
        if val:
            return val
    return None


def extract_script_price(html: str) -> int | None:
    # Цена внутри JS-объектов: "price": 1299 / 'PRICE': '1 299'
    pattern = re.compile(
        r"""["']?(?:price|PRICE|Price)["']?\s*[:=]\s*["']?(\d[\d\s\u00a0.,]*)""")
    for m in pattern.finditer(html):
        val = parse_price(m.group(1))
        if val:
            return val
    return None


def extract_text_price(soup: BeautifulSoup) -> int | None:
    page_text = soup.get_text(" ")
    for m in re.finditer(r"(\d[\d\s\u00a0]{1,8})\s*(?:руб|₽|р\.)", page_text, re.I):
        val = parse_price(m.group(1))
        if val and val >= 100:
            return val
    return None


def get_product_price(url: str) -> int | None:
    try:
        response = fetch_page(url)
        logging.info(f"📡 Статус ответа от сайта для {url}: {response.status_code}")

        if response.status_code != 200:
            logging.warning(f"Тело ответа: {response.text[:500]!r}")
            return None

        # Защита от неверной кодировки
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # Если страница подозрительно короткая, показываем её целиком
        if len(html) < 2000:
            logging.warning(f"⚠️ Короткая страница ({len(html)} символов): {html!r}")

        for name, func in (
            ("structured", lambda: extract_structured_price(soup)),
            ("selectors", lambda: extract_selector_price(soup)),
            ("scripts", lambda: extract_script_price(html)),
            ("text", lambda: extract_text_price(soup)),
        ):
            val = func()
            if val:
                logging.info(f"✅ Цена найдена методом '{name}': {val}")
                return val

        # Ничего не нашли: сохраняем страницу и логируем кандидатов
        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(html)
        logging.warning(f"❌ Не удалось извлечь цену. Страница сохранена в debug.html ({len(html)} символов)")
        for el in soup.find_all(class_=re.compile("price", re.I))[:15]:
            logging.warning(f"   кандидат: <{el.name}> {el.get('class')} -> {el.get_text(strip=True)[:60]!r}")
        return None
    except Exception as e:
        logging.error(f"❌ Ошибка при запросе {url}: {e}")
        return None


async def notifier(bot: Bot):
    while True:
        for user_id, data in list(user_trackers.items()):
            url = data["url"]
            last_price = data["last_price"]

            current_price = await asyncio.to_thread(get_product_price, url)

            if current_price is None:
                continue

            if last_price is None:
                user_trackers[user_id]["last_price"] = current_price
                continue

            if current_price == last_price:
                continue

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
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение {user_id}: {e}")

            # Обновляем цену, если трекер не удалили за время запроса
            if user_id in user_trackers:
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
    initial_price = await asyncio.to_thread(get_product_price, url)

    if initial_price is not None:
        user_trackers[user_id] = {"url": url, "last_price": initial_price}
        await message.answer(f"✅ Товар добавлен! Начальная цена: {initial_price} руб.")
    else:
        await message.answer("❌ Не удалось найти цену на странице.")
