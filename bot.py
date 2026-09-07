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
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8955553619:AAHqVdxHL8l_8VnhbjEwp8Nr3Sp6ddquX-E").strip()

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
# ХРАНИЛИЩА
# ============================================================

autoresponder = {
    "active": False,
    "text": "Привет! Сейчас я занят и отвечу позже."
}

spam_text = None
active_trolls = {}
is_ghouling = {}
notes = {}
active_games = {}


# ============================================================
# FSM
# ============================================================

class AutoresponderState(StatesGroup):
    waiting_for_text = State()


# ============================================================
# ФРАЗЫ ТРОЛЛИНГА
# ============================================================

TROLL_PHRASES = [
    "Спорить с тобой — это как играть в шахматы с голубем.",
    "Ты всегда такой умный или сегодня особенный день?",
    "Ага, очень интересно, продолжай.",
    "Мнение принято.",
    "1000-7..."
]


# ============================================================
# SUPABASE
# ============================================================

async def get_or_create_user(user_id: int, username: str):
    try:
        response = (
            supabase
            .table("profiles")
            .select("*")
            .eq("id", user_id)
            .execute()
        )

        if not response.data:
            new_user = {
                "id": user_id,
                "username": username,
                "balance": 100
            }

            data = (
                supabase
                .table("profiles")
                .insert(new_user)
                .execute()
            )

            if data.data:
                return data.data[0], True

            return None, False

        return response.data[0], False

    except Exception as e:
        logging.error(f"Ошибка Supabase: {e}")
        return None, False


# ============================================================
# КЛАВИАТУРЫ
# ============================================================

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


def get_rps_keyboard(chat_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗿 Камень", callback_data=f"rps_rock_{chat_id}"),
                InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"rps_scissors_{chat_id}"),
                InlineKeyboardButton(text="📄 Бумага", callback_data=f"rps_paper_{chat_id}")
            ]
        ]
    )


def get_post_game_keyboard(chat_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Играть ещё", callback_data=f"rps_restart_{chat_id}")],
            [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"rps_cancel_{chat_id}")]
        ]
    )


# ============================================================
# /START & ПАНЕЛЬ
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

    if spam_text:
        text += f"\n\n⚡ `.spam`:\n{spam_text}"

    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")


# ============================================================
# АВТООТВЕТЧИК CALLBACKS
# ============================================================

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


# ============================================================
# ИНСТРУКЦИЯ
# ============================================================

@dp.callback_query(F.data == "show_help")
async def show_help(callback: CallbackQuery):
    text = (
        "📖 **Команды бота**\n\n"
        "🤖 Автоответчик — Включается через панель.\n"
        "⚡ `.spam текст` — Установить текст быстрого ответа.\n"
        "⚡ `.spam` — Показать текущий текст.\n"
        "👤 `.info` — Показать информацию о собеседнике.\n"
        "🎭 `.a_troll` — Вкл/выкл авто-троллинг.\n"
        "🗿 `.starts` — Запустить игру Камень-Ножницы-Бумага.\n"
        "🔢 `.ghoul` — Запустить 1000-7.\n"
        "🛑 `.ghoulstop` — Остановить 1000-7.\n"
        "📌 `.note имя текст` — Сохранить заметку.\n"
        "📌 `.get имя` — Получить заметку."
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "show_game_info")
async def show_game_info(callback: CallbackQuery):
    await callback.message.answer("🎮 Чтобы начать игру, напиши:\n\n`.starts`", parse_mode="Markdown")
    await callback.answer()


# ============================================================
# ИГРА КНБ
# ============================================================

async def start_rps_game(chat_id: int, business_connection_id: str = None):
    active_games[chat_id] = {
        "choices": {},
        "business_connection_id": business_connection_id,
        "finished": False
    }

    kwargs = {"chat_id": chat_id, "text": "🎮 **КАМЕНЬ • НОЖНИЦЫ • БУМАГА**\n\n👥 Игроков готово: **(0/2)**\n\nСделайте свой выбор ниже:", "reply_markup": get_rps_keyboard(chat_id), "parse_mode": "Markdown"}
    if business_connection_id:
        kwargs["business_connection_id"] = business_connection_id

    await bot.send_message(**kwargs)


def get_winner(choice1, choice2):
    if choice1 == choice2:
        return 0
    if (choice1 == "rock" and choice2 == "scissors") or (choice1 == "scissors" and choice2 == "paper") or (choice1 == "paper" and choice2 == "rock"):
        return 1
    return 2


CHOICE_NAMES = {"rock": "🗿 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}


async def finish_rps_game(chat_id: int):
    if chat_id not in active_games:
        return

    game = active_games[chat_id]
    if game["finished"]:
        return

    game["finished"] = True
    players = list(game["choices"].items())

    if len(players) < 2:
        game["finished"] = False
        return

    player1_id, player1 = players[0]
    player2_id, player2 = players[1]
    c1, c2 = player1["choice"], player2["choice"]

    conn_id = game.get("business_connection_id")
    kwargs_wait = {"chat_id": chat_id, "text": "⏳ **Все игроки готовы!** Подсчитываем результат (2 сек)...", "parse_mode": "Markdown"}
    if conn_id:
        kwargs_wait["business_connection_id"] = conn_id

    await bot.send_message(**kwargs_wait)
    await asyncio.sleep(2)

    winner = get_winner(c1, c2)
    if winner == 0:
        result = "🤝 **НИЧЬЯ!**"
    elif winner == 1:
        result = f"🏆 Победил **{player1['name']}**!"
    else:
        result = f"🏆 Победил **{player2['name']}**!"

    text = f"🎮 **РЕЗУЛЬТАТ ИГРЫ**\n\n👤 {player1['name']}: {CHOICE_NAMES[c1]}\n👤 {player2['name']}: {CHOICE_NAMES[c2]}\n\n{result}"
    kwargs_res = {"chat_id": chat_id, "text": text, "reply_markup": get_post_game_keyboard(chat_id), "parse_mode": "Markdown"}
    if conn_id:
        kwargs_res["business_connection_id"] = conn_id

    await bot.send_message(**kwargs_res)


@dp.callback_query(F.data.startswith("rps_"))
async def process_rps_choice(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer()
        return

    choice = parts[1]
    if choice in ["restart", "cancel"]:
        return

    try:
        chat_id = int(parts[2])
    except ValueError:
        await callback.answer("Ошибка игры.", show_alert=True)
        return

    if chat_id not in active_games or active_games[chat_id]["finished"]:
        await callback.answer("❌ Игра уже закончилась.", show_alert=True)
        return

    game = active_games[chat_id]
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name or callback.from_user.username or "Игрок"

    if user_id in game["choices"]:
        await callback.answer("⚠️ Ты уже сделал выбор!", show_alert=True)
        return

    if len(game["choices"]) >= 2:
        await callback.answer("❌ В этой игре уже 2 игрока.", show_alert=True)
        return

    game["choices"][user_id] = {"choice": choice, "name": user_name}
    count = len(game["choices"])

    await callback.answer(f"Твой выбор: {CHOICE_NAMES[choice]}")

    conn_id = game.get("business_connection_id")

    if count == 1:
        kwargs = {"chat_id": chat_id, "text": f"🎮 **Дуэль: Камень, ножницы, бумага!**\n\nИгрок **{user_name}** сделал ход!\nСтатус: **(1/2 игроков готово)**\nОжидаем второго игрока...", "reply_markup": get_rps_keyboard(chat_id), "parse_mode": "Markdown"}
        if conn_id:
            kwargs["business_connection_id"] = conn_id
        await bot.send_message(**kwargs)
    elif count == 2:
        kwargs = {"chat_id": chat_id, "text": "✅ **(2/2 игроков готово!)**\n\nПодводим итоги...", "parse_mode": "Markdown"}
        if conn_id:
            kwargs["business_connection_id"] = conn_id
        await bot.send_message(**kwargs)
        asyncio.create_task(finish_rps_game(chat_id))


@dp.callback_query(F.data.startswith("rps_restart_"))
async def restart_rps(callback: CallbackQuery):
    try:
        chat_id = int(callback.data.split("_")[2])
    except:
        await callback.answer()
        return

    old_game = active_games.get(chat_id)
    conn_id = old_game.get("business_connection_id") if old_game else None

    await start_rps_game(chat_id, conn_id)
    await callback.answer("Новая игра создана!")


@dp.callback_query(F.data.startswith("rps_cancel_"))
async def cancel_rps(callback: CallbackQuery):
    try:
        chat_id = int(callback.data.split("_")[2])
    except:
        await callback.answer()
        return

    if chat_id in active_games:
        del active_games[chat_id]

    await callback.message.edit_text("❌ **Игра отменена.**", parse_mode="Markdown")
    await callback.answer("Игра завершена.")


# ============================================================
# ЕДИНАЯ ЛОГИКА КОМАНД И ОБРАБОТКИ
# ============================================================

async def handle_custom_logic(chat_id: int, user_id: int, text: str, is_business: bool = False, business_connection_id: str = None):
    global spam_text

    async def send_msg(msg_text: str, **kwargs):
        if is_business and business_connection_id:
            await bot.send_message(chat_id=chat_id, text=msg_text, business_connection_id=business_connection_id, **kwargs)
        else:
            await bot.send_message(chat_id=chat_id, text=msg_text, **kwargs)

    # Команды через точку
    if text.startswith("."):
        if text.startswith(".spam"):
            args = text[5:].strip()
            if not args:
                msg = f"⚡ **Текущий `.spam`:**\n\n{spam_text}" if spam_text else "⚡ `.spam` ещё не настроен.\n\nПример:\n`.spam 55`"
                await send_msg(msg, parse_mode="Markdown")
                return True

            spam_text = args
            await send_msg(f"✅ **`.spam` установлен!**\n\nТеперь ответ:\n{spam_text}", parse_mode="Markdown")
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

        if text == ".starts":
            await start_rps_game(chat_id, business_connection_id)
            return True

    # Реакция на входящие сообщения
    if autoresponder["active"]:
        await send_msg(autoresponder["text"])
    elif spam_text:
        await send_msg(spam_text)

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
