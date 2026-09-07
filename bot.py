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

BOT_TOKEN = os.environ["8955553619:AAGzE7GRAMuccvNEb2DqDgkdvISz4_Tp7zA"]


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

# Автоответчик
autoresponder = {
    "active": False,
    "text": "Привет! Сейчас я занят и отвечу позже."
}

# Текст .spam
spam_text = None

# Авто-троллинг
active_trolls = {}

# ghoul
is_ghouling = {}

# Заметки
notes = {}

# Игры
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
# ГЛАВНАЯ ПАНЕЛЬ
# ============================================================

def get_main_keyboard():

    if autoresponder["active"]:
        ar_text = "🔴 Отключить автоответчик"
    else:
        ar_text = "🟢 Включить автоответчик"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ar_text,
                    callback_data="toggle_ar_panel"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📖 Инструкция",
                    callback_data="show_help"
                ),
                InlineKeyboardButton(
                    text="🎮 Игра",
                    callback_data="show_game_info"
                )
            ]
        ]
    )


# ============================================================
# ПОДТВЕРЖДЕНИЕ ОТКЛЮЧЕНИЯ
# ============================================================

def get_confirm_turnoff_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, отключить",
                    callback_data="confirm_ar_off"
                ),
                InlineKeyboardButton(
                    text="❌ Нет",
                    callback_data="cancel_ar_off"
                )
            ]
        ]
    )


# ============================================================
# КАМЕНЬ НОЖНИЦЫ БУМАГА
# ============================================================

def get_rps_keyboard(chat_id: int):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗿 Камень",
                    callback_data=f"rps_rock_{chat_id}"
                ),
                InlineKeyboardButton(
                    text="✂️ Ножницы",
                    callback_data=f"rps_scissors_{chat_id}"
                ),
                InlineKeyboardButton(
                    text="📄 Бумага",
                    callback_data=f"rps_paper_{chat_id}"
                )
            ]
        ]
    )


def get_post_game_keyboard(chat_id: int):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Играть ещё",
                    callback_data=f"rps_restart_{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отказаться",
                    callback_data=f"rps_cancel_{chat_id}"
                )
            ]
        ]
    )


# ============================================================
# /START
# ============================================================

@dp.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext
):

    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username or "Аноним"

    await get_or_create_user(
        user_id,
        username
    )

    status = (
        "ВКЛЮЧЕН 🟢"
        if autoresponder["active"]
        else "ВЫКЛЮЧЕН 🔴"
    )

    text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🤖 Панель управления\n\n"
        f"Автоответчик: **{status}**"
    )

    if autoresponder["active"]:
        text += (
            f"\n\n💬 Текст:\n"
            f"{autoresponder['text']}"
        )

    if spam_text:
        text += (
            f"\n\n⚡ `.spam`:\n"
            f"{spam_text}"
        )

    await message.answer(
        text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )


# ============================================================
# АВТООТВЕТЧИК
# ============================================================

@dp.callback_query(F.data == "toggle_ar_panel")
async def process_ar_toggle(
    callback: CallbackQuery,
    state: FSMContext
):

    if not autoresponder["active"]:

        await state.set_state(
            AutoresponderState.waiting_for_text
        )

        await callback.message.answer(
            "⌨️ **Напиши текст для автоответчика.**\n\n"
            "Этот текст бот будет отправлять людям, "
            "которые пишут тебе в ЛС.",
            parse_mode="Markdown"
        )

    else:

        await callback.message.answer(
            "⚠️ **Отключить автоответчик?**",
            reply_markup=get_confirm_turnoff_keyboard(),
            parse_mode="Markdown"
        )

    await callback.answer()


@dp.message(AutoresponderState.waiting_for_text)
async def process_ar_text(
    message: Message,
    state: FSMContext
):

    global autoresponder

    text = (message.text or "").strip()

    if not text:
        await message.answer(
            "❌ Текст не может быть пустым."
        )
        return

    autoresponder["active"] = True
    autoresponder["text"] = text

    await state.clear()

    await message.answer(
        "✅ **Автоответчик включён!**\n\n"
        f"💬 Текст:\n{text}",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "confirm_ar_off")
async def confirm_ar_off(callback: CallbackQuery):

    autoresponder["active"] = False

    await callback.message.edit_text(
        "☀️ **Автоответчик отключён.**",
        parse_mode="Markdown"
    )

    await callback.answer(
        "Автоответчик выключен!"
    )


@dp.callback_query(F.data == "cancel_ar_off")
async def cancel_ar_off(callback: CallbackQuery):

    await callback.message.edit_text(
        "👍 Автоответчик остался **включённым**.",
        parse_mode="Markdown"
    )

    await callback.answer()


# ============================================================
# ИНСТРУКЦИЯ
# ============================================================

@dp.callback_query(F.data == "show_help")
async def show_help(callback: CallbackQuery):

    text = (
        "📖 **Команды бота**\n\n"

        "🤖 Автоответчик\n"
        "Включается через панель.\n\n"

        "⚡ `.spam текст`\n"
        "Установить текст быстрого ответа.\n\n"

        "⚡ `.spam`\n"
        "Показать текущий текст.\n\n"

        "👤 `.info`\n"
        "Показать информацию о собеседнике.\n\n"

        "🎭 `.a_troll`\n"
        "Вкл/выкл авто-троллинг.\n\n"

        "🗿 `.starts`\n"
        "Запустить игру Камень-Ножницы-Бумага.\n\n"

        "🔢 `.ghoul`\n"
        "Запустить 1000-7.\n\n"

        "🛑 `.ghoulstop`\n"
        "Остановить 1000-7.\n\n"

        "📌 `.note имя текст`\n"
        "Сохранить заметку.\n\n"

        "📌 `.get имя`\n"
        "Получить заметку."
    )

    await callback.message.answer(
        text,
        parse_mode="Markdown"
    )

    await callback.answer()


@dp.callback_query(F.data == "show_game_info")
async def show_game_info(callback: CallbackQuery):

    await callback.message.answer(
        "🎮 Чтобы начать игру, напиши:\n\n"
        "`.starts`",
        parse_mode="Markdown"
    )

    await callback.answer()


# ============================================================
# ИГРА — СОЗДАНИЕ
# ============================================================

async def start_rps_game(
    chat_id: int,
    business_connection_id: str
):

    active_games[chat_id] = {
        "choices": {},
        "business_connection_id": business_connection_id,
        "finished": False
    }

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🎮 **КАМЕНЬ • НОЖНИЦЫ • БУМАГА**\n\n"
            "👥 Игроков готово: **0/2**\n\n"
            "Каждый игрок должен выбрать свой вариант:"
        ),
        reply_markup=get_rps_keyboard(chat_id),
        business_connection_id=business_connection_id,
        parse_mode="Markdown"
    )


# ============================================================
# РЕЗУЛЬТАТ ИГРЫ
# ============================================================

def get_winner(choice1, choice2):

    if choice1 == choice2:
        return 0

    if (
        (choice1 == "rock" and choice2 == "scissors")
        or
        (choice1 == "scissors" and choice2 == "paper")
        or
        (choice1 == "paper" and choice2 == "rock")
    ):
        return 1

    return 2


CHOICE_NAMES = {
    "rock": "🗿 Камень",
    "scissors": "✂️ Ножницы",
    "paper": "📄 Бумага"
}


async def finish_rps_game(
    chat_id: int
):

    if chat_id not in active_games:
        return

    game = active_games[chat_id]

    if game["finished"]:
        return

    game["finished"] = True

    players = list(
        game["choices"].items()
    )

    if len(players) < 2:
        game["finished"] = False
        return

    player1_id, player1 = players[0]
    player2_id, player2 = players[1]

    c1 = player1["choice"]
    c2 = player2["choice"]

    await bot.send_message(
        chat_id=chat_id,
        text="⏳ **Все игроки готовы!**\n\n"
             "3️⃣\n"
             "2️⃣\n"
             "1️⃣",
        business_connection_id=game["business_connection_id"],
        parse_mode="Markdown"
    )

    await asyncio.sleep(2)

    winner = get_winner(c1, c2)

    if winner == 0:

        result = "🤝 **НИЧЬЯ!**"

    elif winner == 1:

        result = (
            f"🏆 Победил **{player1['name']}**!"
        )

    else:

        result = (
            f"🏆 Победил **{player2['name']}**!"
        )

    text = (
        "🎮 **РЕЗУЛЬТАТ ИГРЫ**\n\n"

        f"👤 {player1['name']}\n"
        f"   {CHOICE_NAMES[c1]}\n\n"

        f"👤 {player2['name']}\n"
        f"   {CHOICE_NAMES[c2]}\n\n"

        f"{result}"
    )

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_post_game_keyboard(chat_id),
        business_connection_id=game["business_connection_id"],
        parse_mode="Markdown"
    )


# ============================================================
# ВЫБОР В ИГРЕ
# ============================================================

@dp.callback_query(
    F.data.startswith("rps_")
)
async def process_rps_choice(
    callback: CallbackQuery
):

    parts = callback.data.split("_")

    if len(parts) < 3:
        await callback.answer()
        return

    choice = parts[1]

    try:
        chat_id = int(parts[2])
    except ValueError:
        await callback.answer(
            "Ошибка игры.",
            show_alert=True
        )
        return

    if chat_id not in active_games:

        await callback.answer(
            "❌ Игра уже закончилась.",
            show_alert=True
        )
        return

    game = active_games[chat_id]

    if game["finished"]:

        await callback.answer(
            "❌ Игра уже закончилась.",
            show_alert=True
        )
        return

    user_id = callback.from_user.id

    user_name = (
        callback.from_user.first_name
        or callback.from_user.username
        or "Игрок"
    )

    # Уже выбрал
    if user_id in game["choices"]:

        await callback.answer(
            "⚠️ Ты уже сделал выбор!",
            show_alert=True
        )
        return

    # Если уже 2 игрока
    if len(game["choices"]) >= 2:

        await callback.answer(
            "❌ В этой игре уже 2 игрока.",
            show_alert=True
        )
        return

    game["choices"][user_id] = {
        "choice": choice,
        "name": user_name
    }

    count = len(game["choices"])

    await callback.answer(
        f"Ты выбрал: {CHOICE_NAMES[choice]}"
    )

    # Первый игрок
    if count == 1:

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ **1/2 игроков готовы!**\n\n"
                "⏳ Ждём второго игрока..."
            ),
            business_connection_id=game[
                "business_connection_id"
            ],
            parse_mode="Markdown"
        )

        return

    # Второй игрок
    if count == 2:

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ **2/2 игроков готовы!**\n\n"
                "⏳ Начинаем игру..."
            ),
            business_connection_id=game[
                "business_connection_id"
            ],
            parse_mode="Markdown"
        )

        asyncio.create_task(
            finish_rps_game(chat_id)
        )


# ============================================================
# ИГРАТЬ ЕЩЁ
# ============================================================

@dp.callback_query(
    F.data.startswith("rps_restart_")
)
async def restart_rps(
    callback: CallbackQuery
):

    try:
        chat_id = int(
            callback.data.split("_")[2]
        )
    except:
        await callback.answer()
        return

    old_game = active_games.get(chat_id)

    if not old_game:
        await callback.answer(
            "Игра не найдена.",
            show_alert=True
        )
        return

    business_connection_id = old_game[
        "business_connection_id"
    ]

    active_games[chat_id] = {
        "choices": {},
        "business_connection_id":
            business_connection_id,
        "finished": False
    }

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🎮 **НОВАЯ ИГРА!**\n\n"
            "👥 Игроков готово: **0/2**\n\n"
            "Выберите вариант:"
        ),
        reply_markup=get_rps_keyboard(chat_id),
        business_connection_id=business_connection_id,
        parse_mode="Markdown"
    )

    await callback.answer(
        "Новая игра!"
    )


# ============================================================
# ОТКАЗАТЬСЯ
# ============================================================

@dp.callback_query(
    F.data.startswith("rps_cancel_")
)
async def cancel_rps(
    callback: CallbackQuery
):

    try:
        chat_id = int(
            callback.data.split("_")[2]
        )
    except:
        await callback.answer()
        return

    if chat_id in active_games:
        del active_games[chat_id]

    await callback.message.answer(
        "❌ **Игра завершена.**",
        parse_mode="Markdown"
    )

    await callback.answer(
        "Игра завершена."
    )


# ============================================================
# BUSINESS MESSAGE
# ============================================================

@dp.business_message()
async def handle_business_message(
    message: Message
):

    global spam_text

    chat_id = message.chat.id

    user_id = message.from_user.id

    text = (
        message.text or ""
    ).strip()

    business_connection_id = (
        message.business_connection_id
    )

    if not business_connection_id:
        return

    # ========================================================
    # ОПРЕДЕЛЯЕМ ВЛАДЕЛЬЦА / СОБЕСЕДНИКА
    # ========================================================

    is_me = user_id != chat_id
    is_partner = not is_me

    # ========================================================
    # КОМАНДЫ ВЛАДЕЛЬЦА
    # ========================================================

    if is_me and text.startswith("."):

        # ----------------------------------------------------
        # .spam
        # ----------------------------------------------------

        if text.startswith(".spam"):

            args = text[5:].strip()

            if not args:

                if spam_text:

                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "⚡ **Текущий `.spam`:**\n\n"
                            f"{spam_text}"
                        ),
                        business_connection_id=
                            business_connection_id,
                        parse_mode="Markdown"
                    )

                else:

                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "⚡ `.spam` ещё не настроен.\n\n"
                            "Пример:\n"
                            "`.spam 55`"
                        ),
                        business_connection_id=
                            business_connection_id,
                        parse_mode="Markdown"
                    )

                return

            spam_text = args

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "✅ **`.spam` установлен!**\n\n"
                    f"Теперь ответ:\n{spam_text}"
                ),
                business_connection_id=
                    business_connection_id,
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # .info
        # ----------------------------------------------------

        if text == ".info":

            user = message.from_user

            username = (
                f"@{user.username}"
                if user.username
                else "отсутствует"
            )

            full_name = (
                user.full_name
                if hasattr(user, "full_name")
                else user.first_name
            )

            info_text = (
                "👤 **ИНФОРМАЦИЯ О СОБЕСЕДНИКЕ**\n\n"

                f"📝 Имя: **{full_name}**\n"
                f"🆔 ID: `{user.id}`\n"
                f"🔗 Username: {username}\n"
                f"🌐 Язык: `{user.language_code or 'не указан'}`\n"
                f"🤖 Бот: "
                f"{'да' if user.is_bot else 'нет'}"
            )

            await bot.send_message(
                chat_id=chat_id,
                text=info_text,
                business_connection_id=
                    business_connection_id,
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # .ghoulstop
        # ----------------------------------------------------

        if text == ".ghoulstop":

            is_ghouling[chat_id] = False

            await bot.send_message(
                chat_id=chat_id,
                text="🛑 **Цикл 1000-7 остановлен.**",
                business_connection_id=
                    business_connection_id,
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # .ghoul
        # ----------------------------------------------------

        if text == ".ghoul":

            if is_ghouling.get(chat_id, False):
                return

            is_ghouling[chat_id] = True

            value = 1000

            while (
                value > 0
                and is_ghouling.get(chat_id, False)
            ):

                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{value} - 7 = {value - 7}",
                    business_connection_id=
                        business_connection_id
                )

                value -= 7

                await asyncio.sleep(0.3)

            is_ghouling[chat_id] = False

            return

        # ----------------------------------------------------
        # .a_troll
        # ----------------------------------------------------

        if text == ".a_troll":

            current = active_trolls.get(
                chat_id,
                False
            )

            active_trolls[chat_id] = not current

            status = (
                "включён 🎭"
                if active_trolls[chat_id]
                else "выключен 🛑"
            )

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🎭 Авто-троллинг **{status}**"
                ),
                business_connection_id=
                    business_connection_id,
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # .note
        # ----------------------------------------------------

        if text.startswith(".note"):

            args = (
                text[5:]
                .strip()
                .split(maxsplit=1)
            )

            if len(args) != 2:

                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "❌ Использование:\n"
                        "`.note имя текст`"
                    ),
                    business_connection_id=
                        business_connection_id,
                    parse_mode="Markdown"
                )

                return

            name = args[0].lower()
            note_text = args[1]

            notes[name] = note_text

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"📌 Заметка **{name}** сохранена."
                ),
                business_connection_id=
                    business_connection_id,
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # .get
        # ----------------------------------------------------

        if text.startswith(".get"):

            name = (
                text[4:]
                .strip()
                .lower()
            )

            if not name:

                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "❌ Использование:\n"
                        "`.get имя`"
                    ),
                    business_connection_id=
                        business_connection_id,
                    parse_mode="Markdown"
                )

                return

            result = notes.get(name)

            if result is None:

                result = (
                    f"❌ Заметка **{name}** не найдена."
                )

            await bot.send_message(
                chat_id=chat_id,
                text=result,
                business_connection_id=
                    business_connection_id,
                parse_mode="Markdown"
            )

            return

        # ----------------------------------------------------
        # .starts
        # ----------------------------------------------------

        if text == ".starts":

            await start_rps_game(
                chat_id,
                business_connection_id
            )

            return

    # ========================================================
    # ВХОДЯЩЕЕ СООБЩЕНИЕ ОТ СОБЕСЕДНИКА
    # ========================================================

    if is_partner:

        # ----------------------------------------------------
        # АВТООТВЕТЧИК
        # ----------------------------------------------------

        if (
            autoresponder["active"]
            and message.chat.type == "private"
        ):

            await bot.send_message(
                chat_id=chat_id,
                text=autoresponder["text"],
                business_connection_id=
                    business_connection_id
            )

            # НЕ return, если хотим чтобы .spam
            # тоже мог работать отдельно

        # ----------------------------------------------------
        # .spam
        # ----------------------------------------------------

        if spam_text:

            await bot.send_message(
                chat_id=chat_id,
                text=spam_text,
                business_connection_id=
                    business_connection_id
            )

        # ----------------------------------------------------
        # АВТО-ТРОЛЛИНГ
        # ----------------------------------------------------

        if active_trolls.get(
            chat_id,
            False
        ):

            await bot.send_message(
                chat_id=chat_id,
                text=random.choice(
                    TROLL_PHRASES
                ),
                business_connection_id=
                    business_connection_id
            )


# ============================================================
# ЗАПУСК
# ============================================================

async def main():

    logging.basicConfig(
        level=logging.INFO
    )

    print("🤖 Бот запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        print("Бот остановлен.")
