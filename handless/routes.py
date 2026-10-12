import asyncio
from email import message
from email.mime import text, image

import aiosqlite
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,callback_query
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram import Bot
from aiogram.types import FSInputFile

router = Router()

#-----

subscribers = set()

async def notifier(bot: Bot):
    while True:
        if subscribers:
            for user_id in list(subscribers):
                try:
                    await bot.send_message(user_id, "diawodawio;dao")
                except Exception:
                    pass

        await asyncio.sleep(1)

@router.message(Command('start'))
async def start(message: Message):
    await message.answer(
        "команды:\n"
        "/subscribe - активация увед\n"
        "/unsubscribe - деактивация увед\n"
        "/subscribers - список"
    )

@router.message(Command('subscribe'))
async def subscribe(message: Message):
    user_id = message.from_user.id

    subscribers.add(user_id)

    await message.answer("вы подписвлис")


@router.message(Command("unsubscribe"))
async def unsubscribe(message: Message):
    user_id = message.from_user.id

    subscribers.discard(user_id)

    await message.answer("вы отподписвлис")

@router.message(Command('subscribers'))
async def subscribers_list(message: Message):
    if not subscribers:
        await message.answer("никого")
        return

    text = "подптсчики\n"
    for uid in subscribers:
        text += f"{uid}\n"
    await message.answer(text)
