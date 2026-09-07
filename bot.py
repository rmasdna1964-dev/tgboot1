import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage

# Настройки и токен
BOT_TOKEN = os.getenv("BOT_TOKEN", "8955553619:AAGPRoVXir741kBwfYcGg6GlJhI4WzezK2Y").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Глобальные переменные
is_spamming = {}
active_games = {}

# --- КЛАВИАТУРЫ ДЛЯ КНБ ---

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
            InlineKeyboardButton(text="❌ Завершить", callback_data=f"rps_cancel_{chat_id}")
        ]
    ])

# --- КОМАНДА /start ---

@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 **Бот активен!**\n\n"
        "Доступные команды:\n"
        "• `.spam <текст>` — Запустить спам с интервалом 3 сек (остановка: `.stop`)\n"
        "• `.play` — Сыграть в Камень, Ножницы, Бумага"
    )
    await message.answer(text, parse_mode="Markdown")

# --- ОБРАБОТЧИКИ КЛИКОВ КНБ ---

@dp.callback_query(lambda c: c.data and (c.data.startswith("rps_restart_") or c.data.startswith("rps_cancel_")))
async def process_post_game_actions(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    action, chat_id = parts[1], int(parts[2])

    if action == "restart":
        active_games[chat_id] = {"choices": {}}
        await callback_query.message.edit_text("🎮 **Камень, ножницы, бумага! Сделайте выбор:**", reply_markup=get_rps_keyboard(chat_id))
    elif action == "cancel":
        if chat_id in active_games:
            del active_games[chat_id]
        try:
            await callback_query.message.delete()
        except Exception:
            await callback_query.message.edit_text("❌ Игра завершена.")

@dp.callback_query(lambda c: c.data and c.data.startswith("rps_"))
async def process_rps_choice(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    choice, chat_id = parts[1], int(parts[2])
    user_id, user_name = callback_query.from_user.id, callback_query.from_user.first_name

    if chat_id not in active_games:
        await callback_query.answer("Игра не найдена. Напишите .play", show_alert=True)
        return

    game = active_games[chat_id]
    game["choices"][user_id] = {"choice": choice, "name": user_name}
    await callback_query.answer(f"Вы выбрали {choice.upper()}!")

    if len(game["choices"]) >= 2:
        await callback_query.message.edit_text("⏳ Подсчитываем результаты...")
        await asyncio.sleep(1)
        players = list(game["choices"].values())
        p1, p2 = players[0], players[1]
        c1, c2 = p1["choice"], p2["choice"]

        if c1 == c2:
            result = "🤝 **Ничья!**"
        elif (c1 == "rock" and c2 == "scissors") or (c1 == "scissors" and c2 == "paper") or (c1 == "paper" and c2 == "rock"):
            result = f"🏆 Победил **{p1['name']}**!"
        else:
            result = f"🏆 Победил **{p2['name']}**!"

        choices_ru = {"rock": "🗿 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}
        res_text = (
            f"🎮 **Результаты игры:**\n\n"
            f"👤 **{p1['name']}**: {choices_ru.get(c1, c1)}\n"
            f"👤 **{p2['name']}**: {choices_ru.get(c2, c2)}\n\n"
            f"{result}"
        )
        await callback_query.message.edit_text(res_text, reply_markup=get_post_game_keyboard(chat_id), parse_mode="Markdown")

# --- ОБРАБОТЧИК ЛОГИКИ TELEGRAM BUSINESS И ОБЫЧНЫХ СООБЩЕНИЙ ---

async def handle_commands(chat_id: int, text: str, business_conn_id: str = None):
    global is_spamming, active_games

    async def send_msg(msg_text: str, **kwargs):
        if business_conn_id:
            await bot.send_message(chat_id=chat_id, text=msg_text, business_connection_id=business_conn_id, **kwargs)
        else:
            await bot.send_message(chat_id=chat_id, text=msg_text, **kwargs)

    if text.startswith("."):
        # Команда .play (Камень, Ножницы, Бумага)
        if text == ".play":
            active_games[chat_id] = {"choices": {}}
            await send_msg(
                "🎮 **Дуэль: Камень, ножницы, бумага!**\nДва игрока должны выбрать фигуру:",
                reply_markup=get_rps_keyboard(chat_id),
                parse_mode="Markdown"
            )
            return True

        # Команда .spam <текст>
        if text.startswith(".spam"):
            msg = text[5:].strip()
            if not msg:
                await send_msg("❌ **Укажите текст:**\n`.spam Текст сообщения`", parse_mode="Markdown")
                return True

            is_spamming[chat_id] = True
            while is_spamming.get(chat_id, False):
                try:
                    await send_msg(msg)
                    await asyncio.sleep(3.0)  # Интервал отправки отправки 3 секунды
                except Exception as e:
                    logging.error(f"Ошибка при спаме: {e}")
                    break
            return True

        # Команда .stop для остановки спама
        if text == ".stop":
            is_spamming[chat_id] = False
            await send_msg("🛑 **Спам остановлен.**", parse_mode="Markdown")
            return True

    return False

@dp.business_message()
async def handle_business_message(message: Message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    conn_id = message.business_connection_id

    if conn_id:
        await handle_commands(chat_id, text, business_conn_id=conn_id)

@dp.message(F.text)
async def handle_regular_message(message: Message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    await handle_commands(chat_id, text)

# --- ЗАПУСК ---

async def main():
    logging.basicConfig(level=logging.INFO)
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
