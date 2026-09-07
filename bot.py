import asyncio
import logging
import random
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

# Вставьте ваш НОВЫЙ токен от BotFather
BOT_TOKEN = "8872260684:AAED-oo-qBqge-nTot8Kva1H4wxjRZvSHSM"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            last_bonus TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id: int, username: str = "Аноним"):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance, last_bonus FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, username, 0))
        conn.commit()
        cursor.execute("SELECT user_id, balance, last_bonus FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    conn.close()
    return user

def update_balance(user_id: int, amount: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def claim_daily_bonus(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT last_bonus FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    
    now = datetime.now()
    if res and res[0]:
        last_bonus_time = datetime.fromisoformat(res[0])
        if now - last_bonus_time < timedelta(hours=24):
            conn.close()
            remaining = timedelta(hours=24) - (now - last_bonus_time)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            return False, f"Бонус уже получен! Зайдите через {hours}ч {minutes}мин."

    cursor.execute("UPDATE users SET balance = balance + 220, last_bonus = ? WHERE user_id = ?", (now.isoformat(), user_id))
    conn.commit()
    conn.close()
    return True, "🎉 Вы получили ежедневный бонус: +220 коинов!"

# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Ежедневный бонус (+220)", callback_data="claim_bonus")],
        [InlineKeyboardButton(text="👤 Профиль / Вывод", callback_data="show_profile")]
    ])

def get_rps_keyboard(game_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗿 Камень", callback_data=f"choice_rock_{game_id}"),
            InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"choice_scissors_{game_id}"),
            InlineKeyboardButton(text="📄 Бумага", callback_data=f"choice_paper_{game_id}")
        ]
    ])

# Хранилище активных игр
active_games = {}

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    get_user(message.from_user.id, message.from_user.first_name)
    text = (
        f"Привет, {message.from_user.first_name}!\n\n"
        "🎮 Напиши `.play` в чат, чтобы начать игру в **Камень, Ножницы, Бумага**.\n"
        "💰 За победу: **+50 коинов**, за поражение: **-10 коинов**.\n"
        "🧸 Накопи **50,000 коинов**, чтобы вывести Мишку за 15 звёзд!"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.message(F.text.startswith(".play"))
async def start_game(message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    get_user(user_id, user_name)

    game_id = f"game_{message.chat.id}_{random.randint(1000, 9999)}"
    active_games[game_id] = {
        "players": {},
        "status": "waiting"
    }

    text = (
        "🎮 **Игра «Камень, ножницы, бумага» началась!**\n\n"
        "Ждем 2 игроков. Нажмите на кнопку ниже, чтобы сделать выбор:"
    )
    await message.answer(text, reply_markup=get_rps_keyboard(game_id), parse_mode="Markdown")

@dp.message(F.text.startswith(".bonus"))
async def bonus_command(message: Message):
    get_user(message.from_user.id, message.from_user.first_name)
    success, msg = claim_daily_bonus(message.from_user.id)
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text.startswith(".profile") | F.text.startswith(".withdraw"))
async def profile_command(message: Message):
    user = get_user(message.from_user.id, message.from_user.first_name)
    balance = user[1]
    
    text = f"👤 **Ваш профиль:**\n💰 Баланс: **{balance} коинов**\n\n"
    if balance >= 50000:
        text += "🧸 **Поздравляем!** У вас достаточно коинов для вывода **Мишки за 15 звёзд**!"
    else:
        text += f"🎯 До вывода Мишки за 15 звёзд осталось: **{50000 - balance} коинов**."
        
    await message.answer(text, parse_mode="Markdown")

# --- ОБРАБОТЧИКИ КНОПОК ---
@dp.callback_query(F.data == "claim_bonus")
async def bonus_callback(callback: CallbackQuery):
    get_user(callback.from_user.id, callback.from_user.first_name)
    success, msg = claim_daily_bonus(callback.from_user.id)
    await callback.answer(msg, show_alert=True)

@dp.callback_query(F.data == "show_profile")
async def profile_callback(callback: CallbackQuery):
    user = get_user(callback.from_user.id, callback.from_user.first_name)
    balance = user[1]
    
    text = f"👤 Профиль:\n💰 Баланс: {balance} коинов\n\n"
    if balance >= 50000:
        text += "🧸 Вы можете забрать Мишку за 15 звёзд!"
    else:
        text += f"🎯 До Мишки осталось: {50000 - balance} коинов."
        
    await callback.answer(text, show_alert=True)

@dp.callback_query(F.data.startswith("choice_"))
async def process_choice(callback: CallbackQuery):
    parts = callback.data.split("_")
    choice = parts[1]
    game_id = f"{parts[2]}_{parts[3]}_{parts[4]}"
    
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    get_user(user_id, user_name)

    if game_id not in active_games:
        await callback.answer("Эта игра уже завершена!", show_alert=True)
        return

    game = active_games[game_id]

    if user_id in game["players"]:
        await callback.answer("Вы уже сделали выбор! Ждем второго игрока.", show_alert=True)
        return

    game["players"][user_id] = {"name": user_name, "choice": choice}
    await callback.answer(f"Вы выбрали: {choice.upper()}!")

    if len(game["players"]) == 1:
        await callback.message.edit_text(
            f"🎮 **Игра идет!**\n\nИгрок **{user_name}** сделал выбор.\nОжидаем второго игрока...",
            reply_markup=get_rps_keyboard(game_id),
            parse_mode="Markdown"
        )

    elif len(game["players"]) == 2:
        await callback.message.edit_text("⏳ Оба игрока сделали выбор! Подсчитываем результаты...")
        
        # Задержка 2 секунды перед оглашением результата
        await asyncio.sleep(2)

        players_list = list(game["players"].items())
        p1_id, p1_data = players_list[0]
        p2_id, p2_data = players_list[1]

        c1, c2 = p1_data["choice"], p2_data["choice"]
        choices_map = {"rock": "🗿 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}

        if c1 == c2:
            result_text = "🤝 **Ничья!** Баланс не изменился."
        elif (c1 == "rock" and c2 == "scissors") or \
             (c1 == "scissors" and c2 == "paper") or \
             (c1 == "paper" and c2 == "rock"):
            
            update_balance(p1_id, 50)
            update_balance(p2_id, -10)
            result_text = (
                f"🏆 Победил **{p1_data['name']}**! (+50 коинов)\n"
                f"💔 **{p2_data['name']}** проиграл. (-10 коинов)"
            )
        else:
            update_balance(p2_id, 50)
            update_balance(p1_id, -10)
            result_text = (
                f"🏆 Победил **{p2_data['name']}**! (+50 коинов)\n"
                f"💔 **{p1_data['name']}** проиграл. (-10 коинов)"
            )

        final_msg = (
            f"🎮 **Результаты дуэли:**\n\n"
            f"👤 **{p1_data['name']}**: {choices_map[c1]}\n"
            f"👤 **{p2_data['name']}**: {choices_map[c2]}\n\n"
            f"{result_text}"
        )

        await callback.message.edit_text(final_msg, parse_mode="Markdown")
        del active_games[game_id]

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
