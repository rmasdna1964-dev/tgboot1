import asyncio
import logging
import random
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client, Client

BOT_TOKEN = "8872260684:AAED-oo-qBqge-nTot8Kva1H4wxjRZvSHSM"
SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

is_spamming = False
is_trolling = False
is_ghouling = False

afk_status = {"active": False, "reason": "Занят"}

class AFKState(StatesGroup):
    waiting_for_text = State()

notes = {}
active_games = {}

TROLL_PHRASES = [
    "Спорить с тобой — это как играть в шахматы с голубем.",
    "Ты всегда такой умный или сегодня особенный день?",
    "Ага, очень интересно, продолжай (нет).",
    "Мнение принято, отправлено в корзину.",
    "1000-7, гуль, получается?"
]

def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💤 Включить автоответчик"),
                KeyboardButton(text="🔴 Отключить автоответчик")
            ],
            [
                KeyboardButton(text="📖 Инструкция"),
                KeyboardButton(text="🎮 Игра")
            ]
        ],
        resize_keyboard=True
    )

def get_confirm_turnoff_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отключить", callback_data="confirm_afk_off"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="cancel_afk_off")
        ]
    ])

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    status_text = f"Статус автоответчика: **{'ВКЛЮЧЕН 🟢' if afk_status['active'] else 'ВЫКЛЮЧЕН 🔴'}**"
    if afk_status["active"]:
        status_text += f"\nТекст: _{afk_status['reason']}_"

    await message.answer(
        f"Панель управления автоответчиком:\n\n{status_text}",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "💤 Включить автоответчик")
async def process_turn_on_afk(message: Message, state: FSMContext):
    await state.set_state(AFKState.waiting_for_text)
    await message.answer(
        "⌨️ **Напишите текст для автоответчика:**\n_(Этот текст будет отправляться собеседникам в ЛС)_", 
        parse_mode="Markdown"
    )

@dp.message(AFKState.waiting_for_text)
async def process_afk_text_input(message: Message, state: FSMContext):
    text = message.text.strip()
    afk_status["active"] = True
    afk_status["reason"] = text
    await state.clear()
    
    await message.answer(
        f"✅ **Автоответчик успешно включен!**\n\nТекст ответа:\n_{text}_",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "🔴 Отключить автоответчик")
async def process_turn_off_afk(message: Message):
    if not afk_status["active"]:
        return

    await message.answer(
        "⚠️ **Точно отключить автоответчик?**",
        reply_markup=get_confirm_turnoff_keyboard(),
        parse_mode="Markdown"
    )

# Подтверждение: ДА (Без сообщений)
@dp.callback_query(F.data == "confirm_afk_off")
async def process_confirm_afk_off(callback_query: CallbackQuery):
    afk_status["active"] = False
    await callback_query.message.delete()
    await callback_query.answer()

# Подтверждение: НЕТ
@dp.callback_query(F.data == "cancel_afk_off")
async def process_cancel_afk_off(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

@dp.message(F.text == "📖 Инструкция")
async def process_help_button(message: Message):
    help_text = (
        "**Все доступные команды (FREE):**\n\n"
        "🐱 `.cat` — Случайное фото котика.\n"
        "⚡ `.ghoul` — Цикл 1000-7.\n"
        "👤 `.info` — Информация о пользователе.\n"
        "🎭 `.a_troll` — Включить/выключить авто-троллинг.\n"
        "💸 `.send [сумма]` — Чек Crypto Bot.\n"
        "📌 `.note [имя] [текст]` / `.get [имя]` — Заметки.\n"
        "🚀 `.spam [текст]` / `.stop` — Спам.\n"
        "🎮 `.starts` — Игра КНБ."
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(F.text == "🎮 Игра")
async def process_game_button(message: Message):
    await message.answer("🎮 Запустите дуэль командой: `.starts`", parse_mode="Markdown")

@dp.business_message()
async def handle_business_message(message: Message):
    global is_spamming, is_trolling, is_ghouling, afk_status
    
    chat_id = message.chat.id
    text = (message.text or "").strip()

    if text.startswith("."):
        if text.startswith(".afk"):
            reason = text[4:].strip() or "Сплю"
            afk_status["active"] = True
            afk_status["reason"] = reason
            await bot.send_message(chat_id=chat_id, text=f"💤 **AFK включен:** {reason}", business_connection_id=message.business_connection_id, parse_mode="Markdown")
            return
        elif text.startswith(".unafk"):
            afk_status["active"] = False
            return

    if afk_status["active"] and message.chat.type == "private":
        await bot.send_message(
            chat_id=chat_id,
            text=afk_status["reason"],
            business_connection_id=message.business_connection_id
        )
        return

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
