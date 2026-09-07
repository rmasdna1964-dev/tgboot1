import asyncio
import logging
import random
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from supabase import create_client, Client

# Настройки и ключи
BOT_TOKEN = "8872260684:AAHEhMfCuLTfG0RK1kjUmDS-TXRiQUWzk"
SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"

# Инициализация Supabase и бота
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Глобальные переменные управления
is_trolling = False
is_ghouling = False

# Хранилище активных фоновых задач спама: {chat_id: asyncio.Task}
active_spams = {}

# Состояние AFK
afk_status = {"active": False, "reason": "Занят"}

# Хранилище заметок и активных игр
notes = {}
active_games = {}

TROLL_PHRASES = [
    "Спорить с тобой — это как играть в шахматы с голубем.",
    "Ты всегда такой умный или сегодня особенный день?",
    "Ага, очень интересно, продолжай (нет).",
    "Мнение принято, отправлено в корзину.",
    "1000-7, гуль, получается?"
]

# Функция фонового спама
async def run_spam_task(chat_id: int, text: str, delay: float, conn_id: str):
    try:
        while True:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                business_connection_id=conn_id
            )
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                await asyncio.sleep(0.05)  # Небольшая пауза для стабильности event loop
    except asyncio.CancelledError:
        # Задача была отменена через .stop
        pass

# Главное меню
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📖 Инструкция", callback_data="show_help"),
            InlineKeyboardButton(text="🎮 Игра", callback_data="show_game_info")
        ]
    ])

def get_rps_keyboard(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗿 Камень", callback_data=f"rps_rock_{chat_id}"),
            InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"rps_scissors_{chat_id}"),
            InlineKeyboardButton(text="📄 Бумага", callback_data=f"rps_paper_{chat_id}")
        ]
    ])

def get_post_game_keyboard(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 Сыграть ещё раз", callback_data=f"rps_restart_{chat_id}"),
            InlineKeyboardButton(text="❌ Не хочу играть", callback_data=f"rps_cancel_{chat_id}")
        ]
    ])

@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = f"Привет! Бот успешно подключен и готов к работе в Telegram Business."
    await message.answer(text, reply_markup=get_main_keyboard())

# Основной обработчик Telegram Business
@dp.business_message()
async def handle_business_message(message: Message):
    global is_trolling, is_ghouling, active_games, afk_status, notes, active_spams
    
    chat_id = message.chat.id
    text = (message.text or "").strip()
    conn_id = message.business_connection_id

    # Проверка: отправлено ли сообщение владельцем бизнес-аккаунта
    is_outgoing = message.from_user.id == message.chat.id or message.is_from_offline

    # 1. Если пишет собеседник (не вы)
    if not is_outgoing:
        if afk_status["active"] and not text.startswith("."):
            await bot.send_message(
                chat_id=chat_id,
                text=f"💤 **Владелец сейчас AFK.**\nПричина: {afk_status['reason']}",
                business_connection_id=conn_id,
                parse_mode="Markdown"
            )
        elif is_trolling and not text.startswith("."):
            await bot.send_message(
                chat_id=chat_id,
                text=random.choice(TROLL_PHRASES),
                business_connection_id=conn_id
            )
        return

    # 2. Если команду пишете ВЫ (Владелец)

    # AFK Управление
    if text.startswith(".afk"):
        reason = text[4:].strip() or "Сплю"
        afk_status["active"] = True
        afk_status["reason"] = reason
        await bot.send_message(
            chat_id=chat_id,
            text=f"💤 **Режим AFK включен.**\nПричина: {reason}",
            business_connection_id=conn_id,
            parse_mode="Markdown"
        )
        return

    elif text == ".unafk":
        afk_status["active"] = False
        await bot.send_message(
            chat_id=chat_id,
            text="☀️ **Режим AFK выключен.**",
            business_connection_id=conn_id,
            parse_mode="Markdown"
        )
        return

    # Управление спамом
    elif text.startswith((".spamkiller", ".killerspam", ".spam")):
        # Если в этом чате уже идет спам — останавливаем предыдущую задачу
        if chat_id in active_spams and not active_spams[chat_id].done():
            active_spams[chat_id].cancel()

        if text.startswith(".spamkiller"):
            msg = text[11:].strip()
            delay = 0.0
        elif text.startswith(".killerspam"):
            msg = text[11:].strip()
            delay = 0.1
        else:
            msg = text[5:].strip()
            delay = 1.5

        if msg:
            # Создаем независимую фоновую задачу для текущего чата
            task = asyncio.create_task(run_spam_task(chat_id, msg, delay, conn_id))
            active_spams[chat_id] = task
        return

    elif text == ".stop":
        if chat_id in active_spams and not active_spams[chat_id].done():
            active_spams[chat_id].cancel()
            del active_spams[chat_id]
            await bot.send_message(
                chat_id=chat_id,
                text="🛑 Спам остановлен.",
                business_connection_id=conn_id
            )
        return

    # Дополнительные команды
    elif text == ".cat":
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.thecatapi.com/v1/images/search") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=data[0]["url"],
                        caption="🐱 Вот твой случайный котик!",
                        business_connection_id=conn_id
                    )
        return

    elif text == ".ghoul":
        if is_ghouling: return
        is_ghouling = True
        val = 1000
        while val > 0 and is_ghouling:
            await bot.send_message(chat_id=chat_id, text=f"{val} - 7 = {val - 7}", business_connection_id=conn_id)
            val -= 7
            await asyncio.sleep(0.3)
            if val < 7: break
        if is_ghouling:
            await bot.send_message(chat_id=chat_id, text="я гуль...", business_connection_id=conn_id)
        is_ghouling = False
        return

    elif text == ".ghoulstop":
        is_ghouling = False
        await bot.send_message(chat_id=chat_id, text="🛑 **Цикл 1000-7 остановлен.**", business_connection_id=conn_id, parse_mode="Markdown")
        return

    elif text == ".a_troll":
        is_trolling = not is_trolling
        status = "включен 🎭" if is_trolling else "выключен 🛑"
        await bot.send_message(chat_id=chat_id, text=f"Режим авто-троллинга **{status}**", business_connection_id=conn_id, parse_mode="Markdown")
        return

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
