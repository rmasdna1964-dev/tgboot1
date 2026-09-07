import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client, Client

# Настройки и ключи
BOT_TOKEN = "8955553619:AAGzE7GRAMuccvNEb2DqDgkdvISz4_Tp7zA"
SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния и хранилища
autoresponder = {"active": True, "text": "Привет! Сейчас я занят, отвечу позже."}
active_trolls = {}
notes = {}
active_games = {} # chat_id: {"choices": {user_id: {"choice": str, "name": str}}}

class AutoresponderState(StatesGroup):
    waiting_for_text = State()

# --- ВЫСПРАВЛЕННАЯ ЛОГИКА ИГРЫ КНБ ---

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

@dp.callback_query(lambda c: c.data and c.data.startswith("rps_"))
async def process_rps(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    action = parts[1]
    chat_id = int(parts[2])
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name

    if action == "restart":
        active_games[chat_id] = {"choices": {}}
        await callback_query.message.edit_text("🎮 **Дуэль: Камень, ножницы, бумага!**\nЖдем ходов игроков... (0/2)", reply_markup=get_rps_keyboard(chat_id), parse_mode="Markdown")
        await callback_query.answer()
        return

    if action == "cancel":
        if chat_id in active_games: 
            del active_games[chat_id]
        await callback_query.message.edit_text("❌ Игра отменена.")
        await callback_query.answer()
        return

    # Выбор варианта (rock / scissors / paper)
    choice = action
    if chat_id not in active_games:
        active_games[chat_id] = {"choices": {}}

    game = active_games[chat_id]
    
    if user_id in game["choices"]:
        await callback_query.answer("Вы уже сделали свой выбор!", show_alert=True)
        return

    game["choices"][user_id] = {"choice": choice, "name": user_name}
    ready_count = len(game["choices"])

    if ready_count == 1:
        await callback_query.answer("Ваш выбор принят!")
        await callback_query.message.edit_text(
            f"🎮 **Дуэль: Камень, ножницы, бумага!**\n\nИгрок **{user_name}** сделал ход!\nГотовность: **(1/2 игроков)**",
            reply_markup=get_rps_keyboard(chat_id),
            parse_mode="Markdown"
        )
    elif ready_count >= 2:
        await callback_query.answer("Ваш выбор принят!")
        await callback_query.message.edit_text("⏳ Все игроки готовы! Подсчитываем результаты (2 сек)...")
        await asyncio.sleep(2)

        players = list(game["choices"].values())
        p1, p2 = players[0], players[1]
        c1, c2 = p1["choice"], p2["choice"]

        moves = {"rock": "🗿 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}

        if c1 == c2:
            result = "🤝 **Ничья!**"
        elif (c1 == "rock" and c2 == "scissors") or (c1 == "scissors" and c2 == "paper") or (c1 == "paper" and c2 == "rock"):
            result = f"🏆 Победил **{p1['name']}**!"
        else:
            result = f"🏆 Победил **{p2['name']}**!"

        res_text = (
            f"🎮 **Результаты дуэли:**\n\n"
            f"👤 **{p1['name']}**: {moves[c1]}\n"
            f"👤 **{p2['name']}**: {moves[c2]}\n\n"
            f"{result}"
        )
        await callback_query.message.edit_text(res_text, reply_markup=get_post_game_keyboard(chat_id), parse_mode="Markdown")

# --- УПРАВЛЕНИЕ БОТОМ В ЛС И TELEGRAM BUSINESS ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    status_text = f"Автоответчик: **{'ВКЛЮЧЕН 🟢' if autoresponder['active'] else 'ВЫКЛЮЧЕН 🔴'}**"
    if autoresponder["active"]:
        status_text += f"\nТекст: _{autoresponder['text']}_"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Изменить автоответчик", callback_data="change_ar")],
        [InlineKeyboardButton(text="🔴 Переключить автоответчик", callback_data="toggle_ar")]
    ])
    await message.answer(f"Панель управления Telegram Business:\n\n{status_text}", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "toggle_ar")
async def toggle_ar_callback(cq: CallbackQuery):
    autoresponder["active"] = not autoresponder["active"]
    status = "включен 🟢" if autoresponder["active"] else "выключен 🔴"
    await cq.message.answer(f"Автоответчик {status}")
    await cq.answer()

@dp.callback_query(F.data == "change_ar")
async def change_ar_callback(cq: CallbackQuery, state: FSMContext):
    await state.set_state(AutoresponderState.waiting_for_text)
    await cq.message.answer("Напишите новый текст для автоответчика:")
    await cq.answer()

@dp.message(AutoresponderState.waiting_for_text)
async def process_ar_text(message: Message, state: FSMContext):
    autoresponder["text"] = message.text.strip()
    autoresponder["active"] = True
    await state.clear()
    await message.answer(f"✅ Новый текст автоответчика сохранен и включен:\n_{autoresponder['text']}_", parse_mode="Markdown")

# --- ОБРАБОТЧИК СООБЩЕНИЙ TELEGRAM BUSINESS ---

@dp.business_message()
async def handle_business_message(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = (message.text or "").strip()
    conn_id = message.business_connection_id

    if not conn_id:
        return

    is_me = (user_id != chat_id)
    is_partner = not is_me

    # Команды, которые вы вводите в любом чате
    if is_me and text.startswith("."):
        if text == ".info":
            user = message.from_user
            info_msg = (
                f"👤 **Информация об аккаунте:**\n\n"
                f"• **Имя:** {user.first_name} {user.last_name or ''}\n"
                f"• **ID:** `{user.id}`\n"
                f"• **Username:** @{user.username if user.username else 'нет'}\n"
                f"• **Premium:** {'Да ⭐' if user.is_premium else 'Нет'}\n"
                f"• **Язык:** {user.language_code or 'неизвестно'}"
            )
            await bot.send_message(chat_id=chat_id, text=info_msg, business_connection_id=conn_id, parse_mode="Markdown")

        elif text == ".starts":
            active_games[chat_id] = {"choices": {}}
            await bot.send_message(
                chat_id=chat_id,
                text="🎮 **Дуэль: Камень, ножницы, бумага!**\nСделайте свой ход (0/2):",
                reply_markup=get_rps_keyboard(chat_id),
                business_connection_id=conn_id,
                parse_mode="Markdown"
            )

        elif text.startswith(".note"):
            args = text[5:].strip().split(maxsplit=1)
            if len(args) == 2:
                notes[args[0].lower()] = args[1]
                await bot.send_message(chat_id=chat_id, text=f"📌 Заметка **'{args[0]}'** сохранена!", business_connection_id=conn_id, parse_mode="Markdown")

        elif text.startswith(".get"):
            note_name = text[4:].strip().lower()
            res = notes.get(note_name, f"❌ Заметка '{note_name}' не найдена.")
            await bot.send_message(chat_id=chat_id, text=res, business_connection_id=conn_id)

    # Реакция на входящие сообщения собеседника
    if is_partner:
        # Работа автоответчика в ЛС
        if autoresponder["active"] and message.chat.type == "private":
            await bot.send_message(chat_id=chat_id, text=autoresponder["text"], business_connection_id=conn_id)

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
