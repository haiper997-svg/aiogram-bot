import asyncio
import logging
import json
import re
import requests
from bs4 import BeautifulSoup
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

router = Router()

# Структура: {user_id: {url: {"last_price": int | None}}}
user_trackers: dict[int, dict[str, dict]] = {}

MAX_ITEMS_PER_USER = 10   # лимит товаров на пользователя
CHECK_INTERVAL = 1800     # проверка раз в 30 минут
PAUSE_BETWEEN_REQUESTS = 2  # пауза между запросами к сайтам, сек

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
URL_RE = re.compile(r"https?://\S+")


# ───────────────────────── Загрузка и парсинг ─────────────────────────

def fetch_page(url: str) -> requests.Response:
    """Загружает страницу, проходя cookie-заглушку хостинга Beget."""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.set("beget", "begetok")

    response = session.get(url, timeout=15)

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
    for el in soup.find_all(attrs={"itemprop": "price"}):
        val = parse_price(el.get("content") or el.get_text())
        if val:
            return val

    for prop in ("product:price:amount", "og:price:amount"):
        meta = soup.find("meta", attrs={"property": prop})
        if meta:
            val = parse_price(meta.get("content"))
            if val:
                return val

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
    for el in soup.select(".product-item-detail-price-current, [id$='_price']"):
        val = parse_price(el.get_text(" ", strip=True))
        if val:
            return val

    for el in soup.find_all(class_=re.compile("price", re.I)):
        classes = " ".join(el.get("class", [])).lower()
        if "old" in classes:
            continue
        val = parse_price(el.get_text(" ", strip=True))
        if val:
            return val
    return None


def extract_script_price(html: str) -> int | None:
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

        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

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

        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(html)
        logging.warning(f"❌ Не удалось извлечь цену. Страница сохранена в debug.html ({len(html)} символов)")
        for el in soup.find_all(class_=re.compile("price", re.I))[:15]:
            logging.warning(f"   кандидат: <{el.name}> {el.get('class')} -> {el.get_text(strip=True)[:60]!r}")
        return None
    except Exception as e:
        logging.error(f"❌ Ошибка при запросе {url}: {e}")
        return None


# ───────────────────────── Уведомления ─────────────────────────

def build_change_text(url: str, old: int, new: int) -> str:
    if new < old:
        return (
            f"🔥 Цена снизилась!\n\n"
            f"🔗 [Ссылка на товар]({url})\n"
            f"📉 Было: {old} руб.\n"
            f"📈 Стало: {new} руб.\n"
            f"💰 Экономия: {old - new} руб."
        )
    return (
        f"📈 Цена выросла!\n\n"
        f"🔗 [Ссылка на товар]({url})\n"
        f"📉 Было: {old} руб.\n"
        f"📈 Стало: {new} руб.\n"
        f"⚠️ Рост на: {new - old} руб."
    )


async def notifier(bot: Bot):
    while True:
        for user_id, items in list(user_trackers.items()):
            for url, item in list(items.items()):
                current_price = await asyncio.to_thread(get_product_price, url)
                await asyncio.sleep(PAUSE_BETWEEN_REQUESTS)

                # Товар могли удалить, пока шёл запрос
                if url not in user_trackers.get(user_id, {}):
                    continue

                if current_price is None:
                    continue

                last_price = item["last_price"]

                if last_price is None:
                    item["last_price"] = current_price
                    continue

                if current_price == last_price:
                    continue

                text = build_change_text(url, last_price, current_price)
                try:
                    await bot.send_message(user_id, text, parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Не удалось отправить сообщение {user_id}: {e}")

                item["last_price"] = current_price

        await asyncio.sleep(CHECK_INTERVAL)


# ───────────────────────── Команды ─────────────────────────

@router.message(Command('start'))
async def start(message: Message):
    await message.answer(
        "🤖 Бот мониторинга цен!\n\n"
        "Отправьте ссылку на товар (или сразу несколько ссылок), "
        "и я начну следить за ценами.\n\n"
        f"Можно отслеживать до {MAX_ITEMS_PER_USER} товаров.\n\n"
        "Команды:\n"
        "/list — список ваших товаров и цены\n"
        "/remove НОМЕР — удалить один товар (номер из /list)\n"
        "/stop — удалить все товары"
    )


@router.message(Command('status', 'list'))
async def show_list(message: Message):
    items = user_trackers.get(message.from_user.id)
    if not items:
        await message.answer("Нет активных отслеживаний.")
        return

    lines = ["📋 Ваши товары:\n"]
    for i, (url, item) in enumerate(items.items(), start=1):
        price = item["last_price"]
        price_text = f"{price} руб." if price is not None else "неизвестна"
        lines.append(f"{i}. {url}\n   🏷 Цена: {price_text}")
    await message.answer("\n".join(lines))


@router.message(Command('remove'))
async def remove_one(message: Message, command: CommandObject):
    user_id = message.from_user.id
    items = user_trackers.get(user_id)
    if not items:
        await message.answer("У вас нет активных отслеживаний.")
        return

    if not command.args or not command.args.strip().isdigit():
        await message.answer("Укажите номер товара из /list, например: /remove 2")
        return

    index = int(command.args.strip())
    urls = list(items.keys())
    if not 1 <= index <= len(urls):
        await message.answer(f"Нет товара с номером {index}. Посмотрите /list.")
        return

    removed_url = urls[index - 1]
    del items[removed_url]
    if not items:
        del user_trackers[user_id]

    await message.answer(f"❌ Удалено:\n{removed_url}")


@router.message(Command('stop'))
async def stop(message: Message):
    user_id = message.from_user.id
    if user_id in user_trackers:
        count = len(user_trackers[user_id])
        del user_trackers[user_id]
        await message.answer(f"❌ Отслеживание остановлено. Удалено товаров: {count}.")
    else:
        await message.answer("У вас нет активных отслеживаний.")


@router.message(F.text.regexp(r"https?://\S+"))
async def catch_product_links(message: Message):
    user_id = message.from_user.id
    urls = list(dict.fromkeys(URL_RE.findall(message.text)))  # без дубликатов, порядок сохранён

    items = user_trackers.setdefault(user_id, {})
    await message.answer("🔍 Проверяю ссылки...")

    report = []
    for url in urls:
        if url in items:
            report.append(f"ℹ️ Уже отслеживается:\n{url}")
            continue

        if len(items) >= MAX_ITEMS_PER_USER:
            report.append(f"⚠️ Лимит {MAX_ITEMS_PER_USER} товаров достигнут, не добавлено:\n{url}")
            continue

        price = await asyncio.to_thread(get_product_price, url)
        if price is not None:
            items[url] = {"last_price": price}
            report.append(f"✅ Добавлено (цена {price} руб.):\n{url}")
        else:
            report.append(f"❌ Не удалось найти цену:\n{url}")

    if not items:
        user_trackers.pop(user_id, None)

    await message.answer("\n\n".join(report))
