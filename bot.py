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
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery
)

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
            balance INTEGER DEFAULT 1000,
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
        cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, username, 1000))
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

# --- ХРАНИЛИЩЕ СОСТОЯНИЙ ИГР И СТАВОК ---
active_games = {}
pending_bets = {}  # {user_id: current_bet_amount}

# --- КЛАВИАТУРЫ ---
def get_bet_keyboard(current_bet: int):
    """Таблица для выбора и настройки ставки от 1 до 1 000 000"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ 1K", callback_data="bet_add_1000"),
            InlineKeyboardButton(text="➕ 10K", callback_data="bet_add_10000"),
            InlineKeyboardButton(text="➕ 100K", callback_data="bet_add_100000")
        ],
        [
            InlineKeyboardButton(text="✖️2 (Удвоить)", callback_data="bet_x2"),
            InlineKeyboardButton(text="🔥 MAX (1M)", callback_data="bet_max"),
            InlineKeyboardButton(text="🔄 Сброс (1)", callback_data="bet_reset")
        ],
        [
            InlineKeyboardButton(text=f"🎮 Подтвердить ставку ({current_bet:,} 💰)", callback_data="bet_confirm")
        ]
    ])

def get_rps_keyboard(game_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗿 Камень", callback_data=f"choice_rock_{game_id}"),
            InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"choice_scissors_{game_id}"),
            InlineKeyboardButton(text="📄 Бумага", callback_data=f"choice_paper_{game_id}")
        ]
    ])

# --- ОБРАБОТКА СТАВОК И ИГРЫ ---
@dp.message(F.text.startswith(".play"))
async def play_command(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.first_name)
    balance = user[1]

    if balance < 1:
        await message.answer("❌ У вас недостаточно коинов для игры! Нажмите `.bonus` или поддержите проект.")
        return

    # Устанавливаем начальную ставку в 1 коин
    pending_bets[user_id] = 1

    text = (
        f"🎯 **Выбор ставки для игры**\n\n"
        f"💰 Ваш баланс: **{balance:,} коинов**\n"
        f"🎲 Текущая ставка: **1 коин**\n\n"
        f"Используйте таблицу ниже, чтобы настроить сумму ставки (от 1 до 1 000 000 коинов):"
    )
    await message.answer(text, reply_markup=get_bet_keyboard(1), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("bet_"))
async def process_bet_selection(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id, callback.from_user.first_name)
    balance = user[1]

    current_bet = pending_bets.get(user_id, 1)
    action = callback.data.replace("bet_", "")

    if action == "add_1000":
        current_bet += 1000
    elif action == "add_10000":
        current_bet += 10000
    elif action == "add_100000":
        current_bet += 100000
    elif action == "x2":
        current_bet *= 2
    elif action == "max":
        current_bet = min(balance, 1000000)
    elif action == "reset":
        current_bet = 1

    # Валидация лимитов (от 1 до 1 000 000 и не больше баланса)
    if current_bet > 1000000:
        current_bet = 1000000
    if current_bet > balance:
        current_bet = balance
    if current_bet < 1:
        current_bet = 1

    pending_bets[user_id] = current_bet

    if action == "confirm":
        # Создаем игру с фиксированной ставкой
        game_id = f"game_{callback.message.chat.id}_{random.randint(1000, 9999)}"
        active_games[game_id] = {
            "bet": current_bet,
            "players": {},
            "status": "waiting"
        }

        await callback.message.edit_text(
            f"🎮 **Игра «Камень, ножницы, бумага» создана!**\n\n"
            f"💰 Ставка игры: **{current_bet:,} коинов**\n"
            f"Ждем 2 игроков. Сделайте свой выбор ниже:",
            reply_markup=get_rps_keyboard(game_id),
            parse_mode="Markdown"
        )
        return

    # Обновляем таблицу ставок
    text = (
        f"🎯 **Выбор ставки для игры**\n\n"
        f"💰 Ваш баланс: **{balance:,} коинов**\n"
        f"🎲 Текущая ставка: **{current_bet:,} коинов**\n\n"
        f"Используйте таблицу ниже, чтобы настроить сумму ставки (от 1 до 1 000 000 коинов):"
    )
    await callback.message.edit_text(text, reply_markup=get_bet_keyboard(current_bet), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("choice_"))
async def process_choice(callback: CallbackQuery):
    parts = callback.data.split("_")
    choice = parts[1]
    game_id = f"{parts[2]}_{parts[3]}_{parts[4]}"
    
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    user = get_user(user_id, user_name)

    if game_id not in active_games:
        await callback.answer("Эта игра уже завершена!", show_alert=True)
        return

    game = active_games[game_id]
    bet = game["bet"]

    if user[1] < bet:
        await callback.answer(f"У вас недостаточно коинов для этой игры! Ставка: {bet:,}", show_alert=True)
        return

    if user_id in game["players"]:
        await callback.answer("Вы уже сделали выбор! Ожидаем второго игрока.", show_alert=True)
        return

    game["players"][user_id] = {"name": user_name, "choice": choice}
    await callback.answer(f"Вы выбрали: {choice.upper()}!")

    if len(game["players"]) == 1:
        await callback.message.edit_text(
            f"🎮 **Дуэль на {bet:,} коинов!**\n\n"
            f"Игрок **{user_name}** сделал выбор.\nОжидаем второго соперника...",
            reply_markup=get_rps_keyboard(game_id),
            parse_mode="Markdown"
        )

    elif len(game["players"]) == 2:
        await callback.message.edit_text("⏳ Оба игрока сделали выбор! Подсчитываем результаты...")
        
        await asyncio.sleep(2)

        players_list = list(game["players"].items())
        p1_id, p1_data = players_list[0]
        p2_id, p2_data = players_list[1]

        c1, c2 = p1_data["choice"], p2_data["choice"]
        choices_map = {"rock": "🗿 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}

        if c1 == c2:
            result_text = "🤝 **Ничья!** Ставки возвращены."
        elif (c1 == "rock" and c2 == "scissors") or \
             (c1 == "scissors" and c2 == "paper") or \
             (c1 == "paper" and c2 == "rock"):
            
            update_balance(p1_id, bet)
            update_balance(p2_id, -bet)
            result_text = (
                f"🏆 Победил **{p1_data['name']}**! (+{bet:,} коинов)\n"
                f"💔 **{p2_data['name']}** проиграл (-{bet:,} коинов)"
            )
        else:
            update_balance(p2_id, bet)
            update_balance(p1_id, -bet)
            result_text = (
                f"🏆 Победил **{p2_data['name']}**! (+{bet:,} коинов)\n"
                f"💔 **{p1_data['name']}** проиграл (-{bet:,} коинов)"
            )

        final_msg = (
            f"🎮 **Результаты дуэли (Ставка: {bet:,} 💰):**\n\n"
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
