import asyncio
import logging
import os
import random
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.client.default import DefaultBotProperties
from supabase import create_client, Client


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("8955553619:AAHqVdxHL8l_8VnhbjEwp8Nr3Sp6ddquX-E", "").strip()

SUPABASE_URL = os.getenv("https://uzdorwhlwihwhvnedwkj.supabase.co", "").strip()
SUPABASE_KEY = os.getenv("sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-", "").strip()

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ============================================================
# ПАМЯТЬ БОТА
# ============================================================

# connection_id -> ID владельца Business аккаунта
business_owners: Dict[str, int] = {}

# connection_id -> информация о владельце
business_connections: Dict[str, Any] = {}

# chat_id -> настройки автоответчика
autoresponders: Dict[int, Dict[str, Any]] = {}

# chat_id -> активная игра
active_games: Dict[int, Dict[str, Any]] = {}

# chat_id -> troll
active_trolls: Dict[int, bool] = {}

# chat_id -> ghoul
is_ghouling: Dict[int, bool] = {}

# chat_id -> заметки
notes: Dict[int, list] = {}


# ============================================================
# FSM
# ============================================================

class AutoResponderState(StatesGroup):
    waiting_text = State()


# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def main_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 Автоответчик",
                    callback_data="panel_autoresponder"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎮 Камень-ножницы-бумага",
                    callback_data="panel_rps"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Помощь",
                    callback_data="panel_help"
                )
            ],
        ]
    )


def autoresponder_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    if enabled:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔴 Отключить автоответчик",
                        callback_data="ar_disable"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✏️ Изменить текст",
                        callback_data="ar_change"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="back_main"
                    )
                ],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🟢 Включить автоответчик",
                    callback_data="ar_enable"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Установить текст",
                    callback_data="ar_change"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back_main"
                )
            ],
        ]
    )


def disable_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, отключить",
                    callback_data="ar_disable_yes"
                ),
                InlineKeyboardButton(
                    text="❌ Нет",
                    callback_data="ar_disable_no"
                )
            ]
        ]
    )


def rps_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🪨 Камень",
                    callback_data=f"rps:rock:{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✂️ Ножницы",
                    callback_data=f"rps:scissors:{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Бумага",
                    callback_data=f"rps:paper:{chat_id}"
                )
            ],
        ]
    )


def rps_after_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Играть ещё",
                    callback_data=f"rps_again:{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отказаться",
                    callback_data=f"rps_cancel:{chat_id}"
                )
            ]
        ]
    )


# ============================================================
# BUSINESS CONNECTION
# ============================================================

async def get_connection_info(connection_id: str):
    """
    Получаем владельца Business подключения.
    """
    if not connection_id:
        return None

    if connection_id in business_connections:
        return business_connections[connection_id]

    try:
        connection = await bot.get_business_connection(
            business_connection_id=connection_id
        )

        business_connections[connection_id] = connection
        business_owners[connection_id] = connection.user.id

        logging.info(
            "Business connection: %s | owner_id=%s | enabled=%s",
            connection_id,
            connection.user.id,
            connection.is_enabled
        )

        return connection

    except Exception:
        logging.exception("Ошибка получения Business Connection")
        return None


async def is_business_owner(message: Message) -> bool:
    """
    Проверяет, является ли отправитель владельцем Business аккаунта.
    """

    connection_id = message.business_connection_id

    if not connection_id:
        return False

    connection = await get_connection_info(connection_id)

    if not connection:
        return False

    if not message.from_user:
        return False

    return message.from_user.id == connection.user.id


# ============================================================
# ОТПРАВКА ОТ ИМЕНИ BUSINESS
# ============================================================

async def business_send(
    chat_id: int,
    text: str,
    connection_id: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None
):
    """
    Отправка сообщения в Business чат.
    """

    kwargs = {
        "chat_id": chat_id,
        "text": text,
    }

    if reply_markup:
        kwargs["reply_markup"] = reply_markup

    if connection_id:
        kwargs["business_connection_id"] = connection_id

    return await bot.send_message(**kwargs)


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer(
        "👻 <b>Теневой бот</b>\n\n"
        "Панель управления:",
        reply_markup=main_panel()
    )


# ============================================================
# ПАНЕЛЬ
# ============================================================

@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.answer()

    try:
        await callback.message.edit_text(
            "👻 <b>Панель управления</b>",
            reply_markup=main_panel()
        )
    except Exception:
        pass


@dp.callback_query(F.data == "panel_help")
async def panel_help(callback: CallbackQuery):
    await callback.answer()

    text = (
        "ℹ️ <b>Команды</b>\n\n"
        "<code>.spam текст</code> — включить автоответчик с указанным текстом\n"
        "<code>.info</code> — информация о собеседнике\n"
        "<code>.starts</code> — начать камень-ножницы-бумага\n"
        "<code>.ghoul</code> — включить режим ghoul\n"
        "<code>.ghoulstop</code> — выключить ghoul\n"
        "<code>.a_troll</code> — включить troll\n"
        "<code>.note текст</code> — сохранить заметку\n"
        "<code>.get</code> — показать заметки"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="back_main"
                        )
                    ]
                ]
            )
        )
    except Exception:
        pass


# ============================================================
# АВТООТВЕТЧИК
# ============================================================

@dp.callback_query(F.data == "panel_autoresponder")
async def panel_autoresponder(callback: CallbackQuery):
    await callback.answer()

    chat_id = callback.message.chat.id

    data = autoresponders.get(
        chat_id,
        {
            "enabled": False,
            "text": "Я сейчас не могу ответить."
        }
    )

    status = "🟢 ВКЛЮЧЕН" if data["enabled"] else "🔴 ВЫКЛЮЧЕН"

    text = (
        "🤖 <b>Автоответчик</b>\n\n"
        f"Статус: <b>{status}</b>\n\n"
        f"Текст:\n<blockquote>{data['text']}</blockquote>"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=autoresponder_keyboard(data["enabled"])
        )
    except Exception:
        pass


@dp.callback_query(F.data == "ar_change")
async def ar_change(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.set_state(AutoResponderState.waiting_text)

    await callback.message.answer(
        "✏️ <b>Напиши новый текст автоответчика:</b>"
    )


@dp.message(AutoResponderState.waiting_text)
async def ar_save_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return

    chat_id = message.chat.id

    autoresponders[chat_id] = {
        "enabled": True,
        "text": text
    }

    await state.clear()

    await message.answer(
        "✅ <b>Автоответчик включён.</b>\n\n"
        f"Теперь на входящие сообщения будет отправляться:\n"
        f"<blockquote>{text}</blockquote>",
        reply_markup=autoresponder_keyboard(True)
    )


@dp.callback_query(F.data == "ar_enable")
async def ar_enable(callback: CallbackQuery):
    await callback.answer("Автоответчик включён")

    chat_id = callback.message.chat.id

    if chat_id not in autoresponders:
        autoresponders[chat_id] = {
            "enabled": True,
            "text": "Я сейчас не могу ответить."
        }
    else:
        autoresponders[chat_id]["enabled"] = True

    await panel_autoresponder(callback)


@dp.callback_query(F.data == "ar_disable")
async def ar_disable(callback: CallbackQuery):
    await callback.answer()

    try:
        await callback.message.edit_text(
            "⚠️ <b>Точно отключить автоответчик?</b>",
            reply_markup=disable_confirm_keyboard()
        )
    except Exception:
        pass


@dp.callback_query(F.data == "ar_disable_yes")
async def ar_disable_yes(callback: CallbackQuery):
    await callback.answer("Отключено")

    chat_id = callback.message.chat.id

    if chat_id not in autoresponders:
        autoresponders[chat_id] = {
            "enabled": False,
            "text": "Я сейчас не могу ответить."
        }
    else:
        autoresponders[chat_id]["enabled"] = False

    await panel_autoresponder(callback)


@dp.callback_query(F.data == "ar_disable_no")
async def ar_disable_no(callback: CallbackQuery):
    await callback.answer()

    await panel_autoresponder(callback)


# ============================================================
# .SPAM
# ============================================================

async def handle_spam_command(
    message: Message,
    connection_id: Optional[str]
):
    """
    .spam 55

    Устанавливает текст автоответчика и сразу включает его.
    """

    text = (message.text or "").strip()

    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await business_send(
            message.chat.id,
            "❌ Использование:\n\n"
            "<code>.spam текст</code>\n\n"
            "Например:\n"
            "<code>.spam Я сейчас отошёл</code>",
            connection_id
        )
        return

    spam_text = parts[1].strip()

    autoresponders[message.chat.id] = {
        "enabled": True,
        "text": spam_text
    }

    await business_send(
        message.chat.id,
        "✅ <b>Автоответчик включён.</b>\n\n"
        f"Текст:\n<blockquote>{spam_text}</blockquote>",
        connection_id
    )


# ============================================================
# .INFO
# ============================================================

async def handle_info(
    message: Message,
    connection_id: Optional[str]
):
    """
    Показывает доступную Telegram информацию о собеседнике.
    """

    user = message.from_user

    if not user:
        await business_send(
            message.chat.id,
            "❌ Не удалось получить информацию.",
            connection_id
        )
        return

    username = (
        f"@{user.username}"
        if user.username
        else "нет"
    )

    full_name = (
        user.full_name
        if hasattr(user, "full_name")
        else f"{user.first_name or ''} {user.last_name or ''}".strip()
    )

    text = (
        "ℹ️ <b>Информация о пользователе</b>\n\n"
        f"👤 Имя: <b>{full_name}</b>\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🔗 Username: {username}\n"
        f"🤖 Bot: {'да' if user.is_bot else 'нет'}\n"
        f"🌐 Язык: <code>{user.language_code or 'не указан'}</code>\n\n"
        f"💬 Chat ID: <code>{message.chat.id}</code>"
    )

    await business_send(
        message.chat.id,
        text,
        connection_id
    )


# ============================================================
# RPS
# ============================================================

RPS_NAMES = {
    "rock": "🪨 Камень",
    "scissors": "✂️ Ножницы",
    "paper": "📄 Бумага"
}


def rps_winner(choice1: str, choice2: str) -> str:
    if choice1 == choice2:
        return "draw"

    wins = {
        "rock": "scissors",
        "scissors": "paper",
        "paper": "rock"
    }

    return "first" if wins[choice1] == choice2 else "second"


async def start_rps(
    chat_id: int,
    connection_id: Optional[str]
):
    active_games[chat_id] = {
        "choices": {},
        "connection_id": connection_id,
        "started": True
    }

    await business_send(
        chat_id,
        "🎮 <b>Камень-ножницы-бумага</b>\n\n"
        "👥 Игроки: <b>0/2 готовы</b>\n\n"
        "Каждый игрок должен выбрать свой вариант.",
        connection_id,
        rps_keyboard(chat_id)
    )


async def finish_rps(
    chat_id: int
):
    game = active_games.get(chat_id)

    if not game:
        return

    choices = game["choices"]

    if len(choices) < 2:
        return

    connection_id = game.get("connection_id")

    await business_send(
        chat_id,
        "✅ <b>2/2 игрока готовы!</b>\n\n"
        "⏳ Определяем победителя...",
        connection_id
    )

    for i in [2, 1]:
        await asyncio.sleep(1)

        try:
            await business_send(
                chat_id,
                f"⏳ <b>{i}</b>",
                connection_id
            )
        except Exception:
            pass

    await asyncio.sleep(0.5)

    players = list(choices.keys())

    player1 = players[0]
    player2 = players[1]

    choice1 = choices[player1]
    choice2 = choices[player2]

    result = rps_winner(choice1, choice2)

    if result == "draw":
        result_text = "🤝 <b>Ничья!</b>"
    elif result == "first":
        result_text = f"🏆 Победил игрок <code>{player1}</code>!"
    else:
        result_text = f"🏆 Победил игрок <code>{player2}</code>!"

    text = (
        "🎮 <b>Результат</b>\n\n"
        f"👤 Игрок 1: <b>{RPS_NAMES[choice1]}</b>\n"
        f"👤 Игрок 2: <b>{RPS_NAMES[choice2]}</b>\n\n"
        f"{result_text}"
    )

    await business_send(
        chat_id,
        text,
        connection_id,
        rps_after_keyboard(chat_id)
    )


@dp.callback_query(F.data.startswith("rps:"))
async def rps_choice(callback: CallbackQuery):
    try:
        _, choice, chat_id_raw = callback.data.split(":")
        chat_id = int(chat_id_raw)
    except Exception:
        await callback.answer("Ошибка игры", show_alert=True)
        return

    if callback.message.chat.id != chat_id:
        await callback.answer("Эта игра уже не здесь.", show_alert=True)
        return

    game = active_games.get(chat_id)

    if not game:
        await callback.answer("Игра уже закончена.", show_alert=True)
        return

    user = callback.from_user

    if user.id in game["choices"]:
        await callback.answer(
            "Ты уже сделал выбор!",
            show_alert=True
        )
        return

    if len(game["choices"]) >= 2:
        await callback.answer(
            "В игре уже 2 игрока.",
            show_alert=True
        )
        return

    game["choices"][user.id] = choice

    count = len(game["choices"])

    await callback.answer(
        f"Выбрано: {RPS_NAMES[choice]}"
    )

    if count == 1:
        try:
            await callback.message.edit_text(
                "🎮 <b>Камень-ножницы-бумага</b>\n\n"
                "👥 Игроки: <b>1/2 готовы</b>\n\n"
                "⏳ Ждём второго игрока...",
                reply_markup=rps_keyboard(chat_id)
            )
        except Exception:
            await business_send(
                chat_id,
                "👥 <b>1/2 игрока готовы.</b>\n\n"
                "⏳ Ждём второго игрока...",
                game.get("connection_id"),
                rps_keyboard(chat_id)
            )

    elif count == 2:
        try:
            await callback.message.edit_text(
                "🎮 <b>Камень-ножницы-бумага</b>\n\n"
                "👥 Игроки: <b>2/2 готовы</b>\n\n"
                "⏳ <b>Игра начинается...</b>"
            )
        except Exception:
            pass

        asyncio.create_task(finish_rps(chat_id))


@dp.callback_query(F.data.startswith("rps_again:"))
async def rps_again(callback: CallbackQuery):
    try:
        _, chat_id_raw = callback.data.split(":")
        chat_id = int(chat_id_raw)
    except Exception:
        await callback.answer("Ошибка", show_alert=True)
        return

    await callback.answer()

    game = active_games.get(chat_id)

    connection_id = (
        game.get("connection_id")
        if game
        else getattr(callback.message, "business_connection_id", None)
    )

    await start_rps(
        chat_id,
        connection_id
    )


@dp.callback_query(F.data.startswith("rps_cancel:"))
async def rps_cancel(callback: CallbackQuery):
    try:
        _, chat_id_raw = callback.data.split(":")
        chat_id = int(chat_id_raw)
    except Exception:
        await callback.answer("Ошибка", show_alert=True)
        return

    await callback.answer("Игра завершена")

    game = active_games.pop(chat_id, None)

    text = "❌ <b>Игра отменена.</b>"

    try:
        await callback.message.edit_text(text)
    except Exception:
        await business_send(
            chat_id,
            text,
            game.get("connection_id") if game else None
        )


# ============================================================
# BUSINESS MESSAGE
# ============================================================

@dp.business_message()
async def business_message_handler(message: Message):
    """
    Основной обработчик сообщений Business аккаунта.
    """

    if not message.business_connection_id:
        return

    connection_id = message.business_connection_id

    connection = await get_connection_info(connection_id)

    if not connection:
        return

    owner_id = connection.user.id
    sender_id = message.from_user.id if message.from_user else None

    # --------------------------------------------------------
    # Если сообщение отправлено ботом/бизнес-ботом — игнорируем
    # --------------------------------------------------------

    if message.sender_business_bot:
        return

    # --------------------------------------------------------
    # ВЛАДЕЛЕЦ
    # --------------------------------------------------------

    if sender_id == owner_id:

        text = (message.text or "").strip()

        if not text:
            return

        lower = text.lower()

        # .spam
        if lower.startswith(".spam"):
            await handle_spam_command(
                message,
                connection_id
            )
            return

        # .info
        if lower == ".info":
            await handle_info(
                message,
                connection_id
            )
            return

        # .starts
        if lower == ".starts":
            await start_rps(
                message.chat.id,
                connection_id
            )
            return

        # .ghoul
        if lower == ".ghoul":
            is_ghouling[message.chat.id] = True

            await business_send(
                message.chat.id,
                "👻 <b>Ghoul включён.</b>",
                connection_id
            )
            return

        # .ghoulstop
        if lower == ".ghoulstop":
            is_ghouling[message.chat.id] = False

            await business_send(
                message.chat.id,
                "👻 <b>Ghoul выключен.</b>",
                connection_id
            )
            return

        # .a_troll
        if lower == ".a_troll":
            active_trolls[message.chat.id] = True

            await business_send(
                message.chat.id,
                "😈 <b>A-Troll включён.</b>",
                connection_id
            )
            return

        # .note
        if lower.startswith(".note"):
            parts = text.split(maxsplit=1)

            if len(parts) < 2:
                await business_send(
                    message.chat.id,
                    "Использование:\n<code>.note текст</code>",
                    connection_id
                )
                return

            note = parts[1]

            notes.setdefault(
                message.chat.id,
                []
            ).append(note)

            await business_send(
                message.chat.id,
                "📝 <b>Заметка сохранена.</b>",
                connection_id
            )
            return

        # .get
        if lower == ".get":
            user_notes = notes.get(
                message.chat.id,
                []
            )

            if not user_notes:
                text_out = "📝 Заметок нет."
            else:
                text_out = (
                    "📝 <b>Заметки:</b>\n\n"
                    + "\n".join(
                        f"{i + 1}. {note}"
                        for i, note in enumerate(user_notes)
                    )
                )

            await business_send(
                message.chat.id,
                text_out,
                connection_id
            )
            return

        # ----------------------------------------------------
        # ВАЖНО:
        # Сообщение владельца не должно запускать автоответчик.
        # ----------------------------------------------------

        return

    # ========================================================
    # ОБЫЧНЫЙ СОБЕСЕДНИК
    # ========================================================

    chat_id = message.chat.id

    # Автоответчик работает НЕЗАВИСИМО от того,
    # онлайн владелец или нет.
    ar = autoresponders.get(chat_id)

    if ar and ar.get("enabled"):

        response_text = ar.get("text")

        if response_text:
            try:
                await business_send(
                    chat_id,
                    response_text,
                    connection_id
                )
            except Exception:
                logging.exception(
                    "Не удалось отправить автоответчик"
                )

        return

    # --------------------------------------------------------
    # GHОUL
    # --------------------------------------------------------

    if is_ghouling.get(chat_id):

        try:
            await business_send(
                chat_id,
                "👻 Ты написал в пустоту...",
                connection_id
            )
        except Exception:
            pass

        return

    # --------------------------------------------------------
    # TROLL
    # --------------------------------------------------------

    if active_trolls.get(chat_id):

        troll_messages = [
            "😈 Я всё вижу.",
            "👀 Интересно...",
            "🤨 Ты точно хотел это написать?",
            "💀 Сообщение принято.",
            "🗿 Понял.",
        ]

        try:
            await business_send(
                chat_id,
                random.choice(troll_messages),
                connection_id
            )
        except Exception:
            pass

        return


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.errors()
async def errors_handler(event):
    logging.exception(
        "Ошибка обработки Telegram события: %s",
        event.exception
    )


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    logging.info("======================================")
    logging.info("      SHADOW BUSINESS BOT START")
    logging.info("======================================")

    me = await bot.get_me()

    logging.info(
        "Бот запущен: @%s | id=%s",
        me.username,
        me.id
    )

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_message",
            "edited_business_message",
            "business_connection"
        ]
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен.")
