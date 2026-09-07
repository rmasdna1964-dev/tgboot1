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
# BUSINESS CONNECTION & SEND
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

async def business_send(
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
# START & PANEL HANDLERS
# ============================================================

@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer("👻 <b>Теневой бот</b>\n\nПанель управления:", reply_markup=main_panel())

@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("👻 <b>Панель управления</b>", reply_markup=main_panel())
    except Exception:
        pass

@dp.callback_query(F.data == "panel_help")
async def panel_help(callback: CallbackQuery):
    await callback.answer()
    text = (
        "ℹ️ <b>Команды управления в чатах:</b>\n\n"
        "<code>.spam текст</code> — установить текст автоответчика\n"
        "<code>.info</code> — информация о собеседнике\n"
        "<code>.starts</code> — начать КНБ\n"
        "<code>.ghoul</code> — режим Ghoul\n"
        "<code>.ghoulstop</code> — выключить Ghoul\n"
        "<code>.a_troll</code> — режим Troll\n"
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

# ============================================================
# АВТООТВЕТЧИК HANDLERS
# ============================================================

@dp.callback_query(F.data == "panel_autoresponder")
async def panel_autoresponder(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id
    data = autoresponders.get(chat_id, {"enabled": False, "text": "Я сейчас не могу ответить."})
    status = "🟢 ВКЛЮЧЕН" if data["enabled"] else "🔴 ВЫКЛЮЧЕН"
    
    text = f"🤖 <b>Автоответчик</b>\n\nСтатус: <b>{status}</b>\n\nТекст:\n<blockquote>{data['text']}</blockquote>"
    try:
        await callback.message.edit_text(text, reply_markup=autoresponder_keyboard(data["enabled"]))
    except Exception:
        pass

@dp.callback_query(F.data == "ar_change")
async def ar_change(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AutoResponderState.waiting_text)
    await callback.message.answer("✏️ <b>Напиши новый текст автоответчика:</b>")

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
        f"✅ <b>Автоответчик включён.</b>\n\nТекст:\n<blockquote>{text}</blockquote>",
        reply_markup=autoresponder_keyboard(True)
    )

@dp.callback_query(F.data == "ar_enable")
async def ar_enable(callback: CallbackQuery):
    await callback.answer("Автоответчик включён")
    chat_id = callback.message.chat.id
    if chat_id not in autoresponders:
        autoresponders[chat_id] = {"enabled": True, "text": "Я сейчас не могу ответить."}
    else:
        autoresponders[chat_id]["enabled"] = True
    await panel_autoresponder(callback)

@dp.callback_query(F.data == "ar_disable")
async def ar_disable(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("⚠️ <b>Точно отключить автоответчик?</b>", reply_markup=disable_confirm_keyboard())
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

# ============================================================
# ОБРАБОТКА ВСЕХ БИЗНЕС СООБЩЕНИЙ
# ============================================================

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

    if message.sender_business_bot:
        return

    # КОМАНДЫ ОТ ВЛАДЕЛЬЦА АККАУНТА
    if sender_id == owner_id:
        text = (message.text or "").strip()
        if not text:
            return

        lower = text.lower()

        if lower.startswith(".spam"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await business_send(message.chat.id, "❌ Укажите текст: <code>.spam текст</code>", connection_id)
                return
            spam_text = parts[1].strip()
            autoresponders[message.chat.id] = {"enabled": True, "text": spam_text}
            await business_send(message.chat.id, f"✅ <b>Автоответчик включён:</b>\n<blockquote>{spam_text}</blockquote>", connection_id)
            return

        if lower == ".info":
            user = message.from_user
            username = f"@{user.username}" if user and user.username else "нет"
            info_text = (
                f"ℹ️ <b>Инфо о собеседнике</b>\n\n"
                f"👤 Имя: <b>{user.full_name if user else 'Неизвестно'}</b>\n"
                f"🆔 ID: <code>{user.id if user else 'N/A'}</code>\n"
                f"🔗 Username: {username}\n"
                f"💬 Chat ID: <code>{message.chat.id}</code>"
            )
            await business_send(message.chat.id, info_text, connection_id)
            return

        if lower == ".ghoul":
            is_ghouling[message.chat.id] = True
            await business_send(message.chat.id, "👻 <b>Ghoul включён.</b>", connection_id)
            return

        if lower == ".ghoulstop":
            is_ghouling[message.chat.id] = False
            await business_send(message.chat.id, "👻 <b>Ghoul выключен.</b>", connection_id)
            return

        if lower == ".a_troll":
            active_trolls[message.chat.id] = True
            await business_send(message.chat.id, "😈 <b>A-Troll включён.</b>", connection_id)
            return

        if lower.startswith(".note"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                notes.setdefault(message.chat.id, []).append(parts[1])
                await business_send(message.chat.id, "📝 <b>Заметка сохранена.</b>", connection_id)
            return

        if lower == ".get":
            user_notes = notes.get(message.chat.id, [])
            out = "📝 Заметок нет." if not user_notes else "📝 <b>Заметки:</b>\n\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(user_notes))
            await business_send(message.chat.id, out, connection_id)
            return

        return

    # РЕАКЦИЯ НА ВХОДЯЩИЕ СООБЩЕНИЯ СОБЕСЕДНИКА
    chat_id = message.chat.id

    ar = autoresponders.get(chat_id)
    if ar and ar.get("enabled") and ar.get("text"):
        try:
            await business_send(chat_id, ar["text"], connection_id)
        except Exception:
            pass
        return

    if is_ghouling.get(chat_id):
        try:
            await business_send(chat_id, "👻 Ты написал в пустоту...", connection_id)
        except Exception:
            pass
        return

    if active_trolls.get(chat_id):
        troll_msgs = ["😈 Я всё вижу.", "👀 Интересно...", "🤨 Ты точно хотел это написать?", "🗿 Понял."]
        try:
            await business_send(chat_id, random.choice(troll_msgs), connection_id)
        except Exception:
            pass
        return

# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    logging.info("Starting Shadow Business Bot...")
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
