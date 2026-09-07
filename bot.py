import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, F
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

user_afk = {}
games = {}  # Хранилище сессий КНБ: {chat_id: {...}}

class AFKState(StatesGroup):
    waiting_for_text = State()

# --- СИНХРОНИЗАЦИЯ С SUPABASE ---
def load_user_settings(user_id: int):
    try:
        res = supabase.table("afk_settings").select("*").eq("user_id", user_id).execute()
        if res.data:
            user_afk[user_id] = {
                "active": res.data[0]["active"],
                "text": res.data[0]["text"]
            }
        else:
            user_afk[user_id] = {"active": False, "text": "Занят"}
    except Exception as e:
        logging.error(f"Ошибка загрузки Supabase: {e}")
        user_afk[user_id] = {"active": False, "text": "Занят"}

def save_user_settings(user_id: int):
    try:
        data = user_afk.get(user_id, {"active": False, "text": "Занят"})
        supabase.table("afk_settings").upsert({
            "user_id": user_id,
            "active": data["active"],
            "text": data["text"]
        }).execute()
    except Exception as e:
        logging.error(f"Ошибка сохранения Supabase: {e}")

# --- КЛАВИАТУРЫ АВТООТВЕТЧИКА ---
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💤 Включить автоответчик"),
                KeyboardButton(text="🔴 Отключить автоответчик")
            ]
        ],
        resize_keyboard=True
    )

def get_confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отключить", callback_data="confirm_off"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="cancel_off")
        ]
    ])

# --- КЛАВИАТУРЫ ИГРЫ КНБ ---
def get_rps_choice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🪨 Камень", callback_data="rps_rock"),
            InlineKeyboardButton(text="✂️ Ножницы", callback_data="rps_scissors"),
            InlineKeyboardButton(text="📄 Бумага", callback_data="rps_paper")
        ]
    ])

def get_rps_restart_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Играть еще", callback_data="rps_restart"),
            InlineKeyboardButton(text="🚪 Выйти из игры", callback_data="rps_exit")
        ]
    ])

# --- ОБРАБОТКА АВТООТВЕТЧИКА В БОТЕ ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    load_user_settings(user_id)
    
    status = "🟢 Включен" if user_afk[user_id]["active"] else "🔴 Выключен"
    await message.answer(
        f"🤖 **Панель автоответчика**\n\nСтатус: {status}\nТекст: `{user_afk[user_id]['text']}`",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "💤 Включить автоответчик")
async def process_turn_on(message: Message, state: FSMContext):
    await state.set_state(AFKState.waiting_for_text)
    await message.answer("⌨️ Напишите текст для автоответчика:")

@dp.message(AFKState.waiting_for_text)
async def process_text_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in user_afk:
        user_afk[user_id] = {}
        
    user_afk[user_id]["active"] = True
    user_afk[user_id]["text"] = message.text.strip()
    save_user_settings(user_id)
    
    await state.clear()
    await message.answer("✅ Автоответчик включен!", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔴 Отключить автоответчик")
async def process_turn_off(message: Message):
    user_id = message.from_user.id
    if user_id not in user_afk:
        load_user_settings(user_id)
    
    if not user_afk[user_id]["active"]:
        return

    await message.answer("⚠️ Точно отключить автоответчик?", reply_markup=get_confirm_keyboard())

@dp.callback_query(F.data == "confirm_off")
async def confirm_off(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in user_afk:
        user_afk[user_id] = {"text": "Занят"}
        
    user_afk[user_id]["active"] = False
    save_user_settings(user_id)
    
    await callback_query.message.delete()
    await callback_query.answer()

@dp.callback_query(F.data == "cancel_off")
async def cancel_off(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

# --- ЛОГИКА ИГРЫ И АВТООТВЕТЧИКА В TELEGRAM BUSINESS ---
@dp.business_message()
async def handle_business_message(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # Запуск игры КНБ
    if text == ".startplay":
        games[chat_id] = {
            "choices": {},       # {user_id: choice}
            "restart_votes": {}, # {user_id: "restart" | "exit"}
            "players": set()     # Участники
        }
        await bot.send_message(
            chat_id=chat_id,
            text="🎮 **Игра «Камень, Ножницы, Бумага» началась!**\nОба игрока, сделайте свой выбор ниже:",
            reply_markup=get_rps_choice_keyboard(),
            business_connection_id=message.business_connection_id,
            parse_mode="Markdown"
        )
        return

    # Автоответчик
    if user_id not in user_afk:
        load_user_settings(user_id)

    if user_afk[user_id]["active"] and message.chat.type == "private":
        await bot.send_message(
            chat_id=message.chat.id,
            text=user_afk[user_id]["text"],
            business_connection_id=message.business_connection_id
        )

# --- ОБРАБОТКА ХОДОВ И КНОПОК ИГРЫ ---
@dp.callback_query(F.data.startswith("rps_"))
async def handle_rps_callbacks(callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name
    data = callback_query.data

    if chat_id not in games:
        await callback_query.answer("⚠️ Игра не найдена или завершена! Напишите .startplay", show_alert=True)
        return

    game = games[chat_id]

    # Выбор фигуры (Камень / Ножницы / Бумага)
    if data in ["rps_rock", "rps_scissors", "rps_paper"]:
        if user_id in game["choices"]:
            await callback_query.answer("Вы уже сделали выбор! Ждём второго игрока...", show_alert=True)
            return

        game["choices"][user_id] = {"choice": data.replace("rps_", ""), "name": user_name}
        game["players"].add(user_id)
        
        await callback_query.answer("Выбор принят!")

        # Первый игрок выбрал — ждем второго
        if len(game["choices"]) == 1:
            await callback_query.message.edit_text(
                f"🎮 **Игра «Камень, Ножницы, Бумага»**\n\n"
                f"✅ **{user_name}** сделал(а) выбор!\n"
                f"⏳ Ожидаем выбор второго игрока...",
                reply_markup=get_rps_choice_keyboard(),
                parse_mode="Markdown"
            )
        # Оба выбрали — объявляем результат через 2 секунды
        elif len(game["choices"]) == 2:
            await callback_query.message.edit_text("⏳ Оба игрока сделали выбор! Подводим итоги...")
            await asyncio.sleep(2)  # Задержка 2 секунды

            p1_id, p2_id = list(game["choices"].keys())
            p1 = game["choices"][p1_id]
            p2 = game["choices"][p2_id]

            names_map = {"rock": "🪨 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}
            c1, c2 = p1["choice"], p2["choice"]

            # Определение победителя
            if c1 == c2:
                winner_text = "🤝 **Ничья!**"
            elif (c1 == "rock" and c2 == "scissors") or \
                 (c1 == "scissors" and c2 == "paper") or \
                 (c1 == "paper" and c2 == "rock"):
                winner_text = f"🏆 Победил(а) **{p1['name']}**!"
            else:
                winner_text = f"🏆 Победил(а) **{p2['name']}**!"

            res_text = (
                f"🏁 **Результаты игры:**\n\n"
                f"👤 {p1['name']}: {names_map[c1]}\n"
                f"👤 {p2['name']}: {names_map[c2]}\n\n"
                f"{winner_text}"
            )

            await callback_query.message.edit_text(
                res_text,
                reply_markup=get_rps_restart_keyboard(),
                parse_mode="Markdown"
            )

    # Выбор продолжения (Играть еще / Выйти)
    elif data in ["rps_restart", "rps_exit"]:
        vote = "restart" if data == "rps_restart" else "exit"
        game["restart_votes"][user_id] = vote

        if len(game["restart_votes"]) == 1:
            action_text = "сыграть ещё раз" if vote == "restart" else "выйти из игры"
            await callback_query.answer(f"Вы выбрали {action_text}. Ждем второго игрока...")
        
        elif len(game["restart_votes"]) == 2:
            votes = list(game["restart_votes"].values())
            
            # Оба хотят рестарт
            if votes[0] == "restart" and votes[1] == "restart":
                game["choices"].clear()
                game["restart_votes"].clear()
                await callback_query.message.edit_text(
                    "🔄 **Новый раунд начался!**\nСделайте свой выбор:",
                    reply_markup=get_rps_choice_keyboard(),
                    parse_mode="Markdown"
                )
            # Оба хотят выйти
            elif votes[0] == "exit" and votes[1] == "exit":
                del games[chat_id]
                await callback_query.message.edit_text("🚪 **Игра завершена.** Спасибо за игру!")
            # Выбрали разные варианты
            else:
                game["restart_votes"].clear()  # Сбрасываем голоса
                await callback_query.answer("⚠️ Выберите одинаковый вариант!", show_alert=True)

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
