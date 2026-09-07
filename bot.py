import asyncio
import logging
import random
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client, Client

# ============================================================
# НАСТРОЙКИ И АВТОМАТИЧЕСКАЯ ПОДСТАНОВКА ТОКЕНА
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    BOT_TOKEN = "8955553619:AAGPRoVXir741kBwfYcGg6GlJhI4WzezK2Y".strip()

SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ============================================================
# ХРАНИЛИЩА И FSM
# ============================================================

autoresponder = {
    "active": False,
    "text": "Привет! Сейчас я занят и отвечу позже."
}

active_trolls = {}
is_ghouling = {}
is_spamming = {}
notes = {}
active_games = {}

class AutoresponderState(StatesGroup):
    waiting_for_text = State()

TROLL_PHRASES = [
    "Спорить с тобой — это как играть в шахматы с голубем.",
    "Ты всегда такой умный или сегодня особенный день?",
    "Ага, очень интересно, продолжай.",
    "Мнение принято.",
    "1000-7..."
]

# ============================================================
# SUPABASE & КЛАВИАТУРЫ
# ============================================================

async def get_or_create_user(user_id: int, username: str):
    try:
        response = supabase.table("profiles").select("*").eq("id", user_id).execute()
        if not response.data:
            new_user = {"id": user_id, "username": username, "balance": 100}
            data = supabase.table("profiles").insert(new_user).execute()
            if data.data:
                return data.data[0], True
            return None, False
        return response.data[0], False
    except Exception as e:
        logging.error(f"Ошибка Supabase: {e}")
        return None, False

def get_main_keyboard():
    ar_text = "🔴 Отключить автоответчик" if autoresponder["active"] else "🟢 Включить автоответчик"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ar_text, callback_data="toggle_ar_panel")],
            [
                InlineKeyboardButton(text="📖 Инструкция", callback_data="show_help"),
                InlineKeyboardButton(text="🎮 Игра", callback_data="show_game_info")
            ]
        ]
    )

def get_confirm_turnoff_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, отключить", callback_data="confirm_ar_off"),
                InlineKeyboardButton(text="❌ Нет", callback_data="cancel_ar_off")
            ]
        ]
    )

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "Аноним"
    await get_or_create_user(user_id, username)

    status = "ВКЛЮЧЕН 🟢" if autoresponder["active"] else "ВЫКЛЮЧЕН 🔴"
    text = f"👋 Привет, {message.from_user.first_name}!\n\n🤖 Панель управления\n\nАвтоответчик: **{status}**"
    if autoresponder["active"]:
        text += f"\n\n💬 Текст:\n{autoresponder['text']}"

    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "toggle_ar_panel")
async def process_ar_toggle(callback: CallbackQuery, state: FSMContext):
    if not autoresponder["active"]:
        await state.set_state(AutoresponderState.waiting_for_text)
        await callback.message.answer("⌨️ **Напиши текст для автоответчика.**", parse_mode="Markdown")
    else:
        await callback.message.answer("⚠️ **Отключить автоответчик?**", reply_markup=get_confirm_turnoff_keyboard(), parse_mode="Markdown")
    await callback.answer()

@dp.message(AutoresponderState.waiting_for_text)
async def process_ar_text(message: Message, state: FSMContext):
    global autoresponder
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return

    autoresponder["active"] = True
    autoresponder["text"] = text
    await state.clear()
    await message.answer(f"✅ **Автоответчик включён!**\n\n💬 Текст:\n{text}", reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "confirm_ar_off")
async def confirm_ar_off(callback: CallbackQuery):
    autoresponder["active"] = False
    await callback.message.edit_text("☀️ **Автоответчик отключён.**", parse_mode="Markdown")
    await callback.answer("Автоответчик выключен!")

@dp.callback_query(F.data == "cancel_ar_off")
async def cancel_ar_off(callback: CallbackQuery):
    await callback.message.edit_text("👍 Автоответчик остался **включённым**.", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "show_help")
async def show_help(callback: CallbackQuery):
    text = (
        "📖 **Команды бота**\n\n"
        "⚡ `.spam <кол-во> <текст>` — Моментальный спам сообщениями.\n"
        "🛑 `.stopspam` — Остановить спам.\n"
        "🤖 Автоответчик — Переключается в меню.\n"
        "👤 `.info` — Информация о собеседнике.\n"
        "🎭 `.a_troll` — Вкл/выкл авто-троллинг.\n"
        "🔢 `.ghoul` — Запустить 1000-7.\n"
        "🛑 `.ghoulstop` — Остановить 1000-7.\n"
        "📌 `.note имя текст` — Сохранить заметку.\n"
        "📌 `.get имя` — Получить заметку."
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# ============================================================
# ЕДИНАЯ ЛОГИКА КОМАНД И МОМЕНТАЛЬНОГО СПАМА
# ============================================================

async def handle_custom_logic(chat_id: int, user_id: int, text: str, is_business: bool = False, business_connection_id: str = None):
    async def send_msg(msg_text: str, **kwargs):
        if is_business and business_connection_id:
            await bot.send_message(chat_id=chat_id, text=msg_text, business_connection_id=business_connection_id, **kwargs)
        else:
            await bot.send_message(chat_id=chat_id, text=msg_text, **kwargs)

    # Работа с командами через точку
    if text.startswith("."):
        if text.startswith(".spam"):
            parts = text[5:].strip().split(maxsplit=1)
            if len(parts) < 2 or not parts[0].isdigit():
                await send_msg("❌ **Формат команды:**\n`.spam 10 Текст для спама`", parse_mode="Markdown")
                return True

            count = int(parts[0])
            spam_msg = parts[1]

            if count <= 0:
                await send_msg("❌ Количество должно быть больше 0.")
                return True

            count = min(count, 100)
            is_spamming[chat_id] = True

            await send_msg(f"🚀 **Запуск спама:** {count} сообщений...", parse_mode="Markdown")

            for _ in range(count):
                if not is_spamming.get(chat_id, False):
                    break
                try:
                    await send_msg(spam_msg)
                except Exception as e:
                    logging.error(f"Ошибка при спаме: {e}")
                    break

            is_spamming[chat_id] = False
            return True

        if text == ".stopspam":
            is_spamming[chat_id] = False
            await send_msg("🛑 **Спам остановлен.**", parse_mode="Markdown")
            return True

        if text == ".info":
            chat = await bot.get_chat(chat_id)
            username = f"@{chat.username}" if chat.username else "отсутствует"
            first_name = chat.first_name or "Не указано"
            last_name = chat.last_name or ""
            full_name = f"{first_name} {last_name}".strip()

            info_text = (
                f"👤 **ИНФОРМАЦИЯ О СОБЕСЕДНИКЕ**\n\n"
                f"📝 Имя: **{full_name}**\n"
                f"🆔 ID: `{chat.id}`\n"
                f"🔗 Username: {username}\n"
                f"💬 Тип чата: `{chat.type}`"
            )
            await send_msg(info_text, parse_mode="Markdown")
            return True

        if text == ".ghoulstop":
            is_ghouling[chat_id] = False
            await send_msg("🛑 **Цикл 1000-7 остановлен.**", parse_mode="Markdown")
            return True

        if text == ".ghoul":
            if is_ghouling.get(chat_id, False):
                return True
            is_ghouling[chat_id] = True
            value = 1000
            while value > 0 and is_ghouling.get(chat_id, False):
                await send_msg(f"{value} - 7 = {value - 7}")
                value -= 7
                await asyncio.sleep(0.3)
            is_ghouling[chat_id] = False
            return True

        if text == ".a_troll":
            current = active_trolls.get(chat_id, False)
            active_trolls[chat_id] = not current
            status = "включён 🎭" if active_trolls[chat_id] else "выключен 🛑"
            await send_msg(f"🎭 Авто-троллинг **{status}**", parse_mode="Markdown")
            return True

        if text.startswith(".note"):
            args = text[5:].strip().split(maxsplit=1)
            if len(args) != 2:
                await send_msg("❌ Использование:\n`.note имя текст`", parse_mode="Markdown")
                return True
            name, note_text = args[0].lower(), args[1]
            notes[name] = note_text
            await send_msg(f"📌 Заметка **{name}** сохранена.", parse_mode="Markdown")
            return True

        if text.startswith(".get"):
            name = text[4:].strip().lower()
            if not name:
                await send_msg("❌ Использование:\n`.get имя`", parse_mode="Markdown")
                return True
            result = notes.get(name, f"❌ Заметка **{name}** не найдена.")
            await send_msg(result, parse_mode="Markdown")
            return True

    # Реакция на входящие сообщения
    if autoresponder["active"]:
        await send_msg(autoresponder["text"])

    if active_trolls.get(chat_id, False):
        await send_msg(random.choice(TROLL_PHRASES))

    return False

@dp.business_message()
async def handle_business_message(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = (message.text or "").strip()
    conn_id = message.business_connection_id

    if not conn_id:
        return

    await handle_custom_logic(chat_id, user_id, text, is_business=True, business_connection_id=conn_id)

@dp.message(F.text)
async def handle_regular_message(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = (message.text or "").strip()

    await handle_custom_logic(chat_id, user_id, text, is_business=False)

# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    logging.basicConfig(level=logging.INFO)
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
