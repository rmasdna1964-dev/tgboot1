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


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or 0)

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Добавь BOT_TOKEN в Secrets/Environment Variables."
    )


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


# ============================================================
# ПАМЯТЬ БОТА
# ============================================================

business_owners: Dict[str, int] = {}
business_connections: Dict[str, Any] = {}
autoresponders: Dict[int, Dict[str, Any]] = {}
active_games: Dict[int, Dict[str, Any]] = {}
active_trolls: Dict[int, bool] = {}
is_ghouling: Dict[int, bool] = {}
notes: Dict[int, list] = {}
active_spams: Dict[int, bool] = {}


# ============================================================
# FSM И КЛАВИАТУРЫ
# ============================================================

class AutoResponderState(StatesGroup):
    waiting_text = State()


def main_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Автоответчик", callback_data="panel_autoresponder")],
            [InlineKeyboardButton(text="🎮 Камень-ножницы-бумага", callback_data="panel_rps")],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="panel_help")],
        ]
    )


def autoresponder_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    btn_text = "🔴 Отключить автоответчик" if enabled else "🟢 Включить автоответчик"
    btn_action = "ar_disable" if enabled else "ar_enable"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data=btn_action)],
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="ar_change")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
        ]
    )


def disable_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, отключить", callback_data="ar_disable_yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="ar_disable_no")
            ]
        ]
    )


def rps_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪨 Камень", callback_data=f"rps:rock:{chat_id}")],
            [InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"rps:scissors:{chat_id}")],
            [InlineKeyboardButton(text="📄 Бумага", callback_data=f"rps:paper:{chat_id}")],
        ]
    )


def rps_after_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Играть ещё", callback_data=f"rps_again:{chat_id}")],
            [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"rps_cancel:{chat_id}")]
        ]
    )


# ============================================================
# ВПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

async def get_connection_info(connection_id: str):
    if not connection_id:
        return None

    if connection_id in business_connections:
        return business_connections[connection_id]

    try:
        connection = await bot.get_business_connection(business_connection_id=connection_id)
        business_connections[connection_id] = connection
        business_owners[connection_id] = connection.user.id
        return connection
    except Exception:
        logging.exception("Ошибка получения Business Connection")
        return None


async def send_reply(
    chat_id: int,
    text: str,
    connection_id: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None
):
    kwargs = {"chat_id": chat_id, "text": text}
    if reply_markup:
        kwargs["reply_markup"] = reply_markup
    if connection_id:
        kwargs["business_connection_id"] = connection_id

    return await bot.send_message(**kwargs)


# ============================================================
# КАМЕНЬ-НОЖНИЦЫ-БУМАГА (RPS)
# ============================================================

RPS_NAMES = {"rock": "🪨 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}

def rps_winner(choice1: str, choice2: str) -> str:
    if choice1 == choice2:
        return "draw"
    wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    return "first" if wins[choice1] == choice2 else "second"


async def start_rps(chat_id: int, connection_id: Optional[str] = None):
    active_games[chat_id] = {"choices": {}, "connection_id": connection_id, "started": True}
    await send_reply(
        chat_id,
        "🎮 <b>Камень-ножницы-бумага</b>\n\n👥 Игроки: <b>0/2 готовы</b>\n\nСделайте свой выбор ниже:",
        connection_id,
        rps_keyboard(chat_id)
    )


async def finish_rps(chat_id: int):
    game = active_games.get(chat_id)
    if not game or len(game["choices"]) < 2:
        return

    connection_id = game.get("connection_id")
    await send_reply(chat_id, "✅ <b>2/2 игрока готовы!</b>\n\n⏳ Определяем победителя...", connection_id)

    for i in [2, 1]:
        await asyncio.sleep(1)
        try:
            await send_reply(chat_id, f"⏳ <b>{i}</b>", connection_id)
        except Exception:
            pass

    await asyncio.sleep(0.5)
    players = list(game["choices"].keys())
    choice1, choice2 = game["choices"][players[0]], game["choices"][players[1]]
    result = rps_winner(choice1, choice2)

    if result == "draw":
        result_text = "🤝 <b>Ничья!</b>"
    elif result == "first":
        result_text = f"🏆 Победил игрок <code>{players[0]}</code>!"
    else:
        result_text = f"🏆 Победил игрок <code>{players[1]}</code>!"

    text = (
        f"🎮 <b>Результат</b>\n\n"
        f"👤 Игрок 1: <b>{RPS_NAMES[choice1]}</b>\n"
        f"👤 Игрок 2: <b>{RPS_NAMES[choice2]}</b>\n\n"
        f"{result_text}"
    )
    await send_reply(chat_id, text, connection_id, rps_after_keyboard(chat_id))


# ============================================================
# ЛОГИКА СЕКРЕТАРЯ И СПАМА
# ============================================================

async def handle_secretary_logic(message: Message, is_owner: bool, connection_id: Optional[str] = None):
    text = (message.text or "").strip()
    chat_id = message.chat.id
    lower = text.lower()

    # 1. ЕСЛИ ПИШЕТ ВЛАДЕЛЕЦ
    if is_owner:
        # КОМАНДА БЕСКОНЕЧНОГО СПАМА (.spam текст)
        if lower.startswith(".spam"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await send_reply(chat_id, "❌ Укажи текст: <code>.spam слово</code>", connection_id)
                return

            spam_text = parts[1].strip()
            active_spams[chat_id] = True

            async def run_spam():
                while active_spams.get(chat_id, False):
                    try:
                        await send_reply(chat_id, spam_text, connection_id)
                    except Exception as e:
                        logging.error(f"Пауза из-за ограничения Telegram: {e}")
                        await asyncio.sleep(0.5)

            asyncio.create_task(run_spam())
            return

        # ОСТАНОВКА СПАМА (.stop)
        if lower == ".stop":
            active_spams[chat_id] = False
            await send_reply(chat_id, "🛑 <b>Спам остановлен.</b>", connection_id)
            return

        # ИНФО О ПОЛЬЗОВАТЕЛЕ (.info)
        if lower == ".info":
            user = message.from_user
            username = f"@{user.username}" if user and user.username else "нет"
            info_text = (
                f"ℹ️ <b>Информация о собеседнике</b>\n\n"
                f"👤 Имя: <b>{user.full_name if user else 'Неизвестно'}</b>\n"
                f"🆔 ID: <code>{user.id if user else 'N/A'}</code>\n"
                f"🔗 Username: {username}\n"
                f"💬 Chat ID: <code>{chat_id}</code>"
            )
            await send_reply(chat_id, info_text, connection_id)
            return

        # ЗАПУСК КНБ (.starts)
        if lower == ".starts":
            await start_rps(chat_id, connection_id)
            return

        # РЕЖИМ GHOUL (.ghoul / .ghoulstop)
        if lower == ".ghoul":
            is_ghouling[chat_id] = True
            await send_reply(chat_id, "👻 <b>Режим Ghoul включён.</b>", connection_id)
            return

        if lower == ".ghoulstop":
            is_ghouling[chat_id] = False
            await send_reply(chat_id, "👻 <b>Режим Ghoul выключен.</b>", connection_id)
            return

        # ТРОЛЛЬ-РЕЖИМ (.a_troll)
        if lower == ".a_troll":
            active_trolls[chat_id] = True
            await send_reply(chat_id, "😈 <b>Тролль-режим включён.</b>", connection_id)
            return

        # ЗАМЕТКИ (.note / .get)
        if lower.startswith(".note"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                notes.setdefault(chat_id, []).append(parts[1].strip())
                await send_reply(chat_id, "📝 <b>Заметка сохранена.</b>", connection_id)
            return

        if lower == ".get":
            user_notes = notes.get(chat_id, [])
            out = "📝 Заметок нет." if not user_notes else "📝 <b>Заметки:</b>\n\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(user_notes))
            await send_reply(chat_id, out, connection_id)
            return

        return

    # 2. ЕСЛИ ПИШЕТ СОБЕСЕДНИК (АВТООТВЕТЧИК И РЕЖИМЫ)
    ar = autoresponders.get(chat_id)
    if ar and ar.get("enabled") and ar.get("text"):
        try:
            await send_reply(chat_id, ar["text"], connection_id)
        except Exception:
            pass
        return

    if is_ghouling.get(chat_id):
        try:
            await send_reply(chat_id, "👻 Ты написал в пустоту...", connection_id)
        except Exception:
            pass
        return

    if active_trolls.get(chat_id):
        troll_msgs = ["😈 Я всё вижу.", "👀 Интересно...", "🤨 Ты точно хотел это написать?", "🗿 Понял."]
        try:
            await send_reply(chat_id, random.choice(troll_msgs), connection_id)
        except Exception:
            pass
        return


# ============================================================
# ПАНЕЛЬ И CALLBACKS
# ============================================================

@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer("👻 <b>Панель управления Секретарем</b>", reply_markup=main_panel())


@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("👻 <b>Панель управления Секретарем</b>", reply_markup=main_panel())
    except Exception:
        pass


@dp.callback_query(F.data == "panel_help")
async def panel_help(callback: CallbackQuery):
    await callback.answer()
    text = (
        "ℹ️ <b>Команды Владельца:</b>\n\n"
        "<code>.spam слово</code> — бесконечный спам сообщением\n"
        "<code>.stop</code> — остановить спам\n"
        "<code>.info</code> — инфо о собеседнике\n"
        "<code>.starts</code> — начать КНБ\n"
        "<code>.ghoul</code> — режим ghoul\n"
        "<code>.ghoulstop</code> — выключить ghoul\n"
        "<code>.a_troll</code> — включить troll\n"
        "<code>.note текст</code> — сохранить заметку\n"
        "<code>.get</code> — показать заметки"
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]])
        )
    except Exception:
        pass


@dp.callback_query(F.data == "panel_autoresponder")
async def panel_autoresponder(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id
    data = autoresponders.get(chat_id, {"enabled": False, "text": "Я сейчас не могу ответить."})
    status = "🟢 ВКЛЮЧЕН" if data["enabled"] else "🔴 ВЫКЛЮЧЕН"
    text = f"🤖 <b>Автоответчик</b>\n\nСтатус: <b>{status}</b>\n\nТекст секретаря:\n<blockquote>{data['text']}</blockquote>"
    try:
        await callback.message.edit_text(text, reply_markup=autoresponder_keyboard(data["enabled"]))
    except Exception:
        pass


@dp.callback_query(F.data == "ar_change")
async def ar_change(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AutoResponderState.waiting_text)
    await callback.message.answer("✏️ <b>Напиши текст, который секретарь будет отправлять людям:</b>")


@dp.message(AutoResponderState.waiting_text)
async def ar_save_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return

    chat_id = message.chat.id
    autoresponders[chat_id] = {"enabled": True, "text": text}
    await state.clear()
    await message.answer(
        f"✅ <b>Автоответчик включён.</b>\n\nСекретарь отвечает:\n<blockquote>{text}</blockquote>",
        reply_markup=autoresponder_keyboard(True)
    )


@dp.callback_query(F.data == "ar_enable")
async def ar_enable(callback: CallbackQuery):
    await callback.answer("Секретарь включён")
    chat_id = callback.message.chat.id
    autoresponders.setdefault(chat_id, {})["enabled"] = True
    if "text" not in autoresponders[chat_id]:
        autoresponders[chat_id]["text"] = "Я сейчас не могу ответить."
    await panel_autoresponder(callback)


@dp.callback_query(F.data == "ar_disable")
async def ar_disable(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("⚠️ <b>Отключить секретаря?</b>", reply_markup=disable_confirm_keyboard())
    except Exception:
        pass


@dp.callback_query(F.data == "ar_disable_yes")
async def ar_disable_yes(callback: CallbackQuery):
    await callback.answer("Отключено")
    chat_id = callback.message.chat.id
    autoresponders.setdefault(chat_id, {})["enabled"] = False
    await panel_autoresponder(callback)


@dp.callback_query(F.data == "ar_disable_no")
async def ar_disable_no(callback: CallbackQuery):
    await callback.answer()
    await panel_autoresponder(callback)


@dp.callback_query(F.data.startswith("rps:"))
async def rps_choice(callback: CallbackQuery):
    try:
        _, choice, chat_id_raw = callback.data.split(":")
        chat_id = int(chat_id_raw)
    except Exception:
        await callback.answer("Ошибка игры", show_alert=True)
        return

    game = active_games.get(chat_id)
    if not game:
        await callback.answer("Игра завершена.", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id in game["choices"]:
        await callback.answer("Выбор уже сделан!", show_alert=True)
        return

    game["choices"][user_id] = choice
    await callback.answer(f"Выбрано: {RPS_NAMES[choice]}")

    if len(game["choices"]) == 2:
        asyncio.create_task(finish_rps(chat_id))


@dp.callback_query(F.data.startswith("rps_again:"))
async def rps_again(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    await callback.answer()
    await start_rps(chat_id)


@dp.callback_query(F.data.startswith("rps_cancel:"))
async def rps_cancel(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    await callback.answer("Игра завершена")
    active_games.pop(chat_id, None)
    try:
        await callback.message.edit_text("❌ <b>Игра отменена.</b>")
    except Exception:
        pass


# ============================================================
# ОБРАБОТКА ЛС И BUSINESS-СООБЩЕНИЙ
# ============================================================

@dp.message(F.chat.type == "private")
async def private_message_handler(message: Message):
    if await dp.storage.get_state(bot=bot, key=message.chat.id):
        return

    is_owner = (OWNER_ID == 0) or (message.from_user and message.from_user.id == OWNER_ID)
    await handle_secretary_logic(message, is_owner=is_owner)


@dp.business_message()
async def business_message_handler(message: Message):
    connection_id = message.business_connection_id
    if not connection_id:
        return

    connection = await get_connection_info(connection_id)
    if not connection:
        return

    owner_id = connection.user.id
    sender_id = message.from_user.id if message.from_user else None
    
    is_owner = (sender_id == owner_id) or (OWNER_ID != 0 and sender_id == OWNER_ID)

    await handle_secretary_logic(message, is_owner=is_owner, connection_id=connection_id)


@dp.errors()
async def errors_handler(event):
    logging.exception("Ошибка обработки события: %s", event.exception)


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    logging.info("======================================")
    logging.info("      SHADOW SECRETARY BOT START")
    logging.info("======================================")

    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    logging.info("Бот запущен: @%s | id=%s", me.username, me.id)

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
