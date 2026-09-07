import asyncio
import logging
import os
import random
import aiosqlite
from typing import Optional, Dict, Any

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
# НАСТРОЙКИ И ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Укажи свой Telegram ID для доступа к администрированию через ЛС
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or 0)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Добавь BOT_TOKEN в переменные окружения.")

DB_PATH = "bot_database.db"

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

# Кеш для Business Connections в оперативной памяти
business_connections: Dict[str, Any] = {}

# ============================================================
# РАБОТА С БАЗОЙ ДАННЫХ (SQLite)
# ============================================================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица настроек чата (автоответчик, режими ghoul/troll)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                ar_enabled INTEGER DEFAULT 0,
                ar_text TEXT DEFAULT 'Я сейчас не могу ответить.',
                is_ghoul INTEGER DEFAULT 0,
                is_troll INTEGER DEFAULT 0
            )
        """)
        # Таблица заметок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                text TEXT
            )
        """)
        await db.commit()

async def get_chat_settings(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ar_enabled, ar_text, is_ghoul, is_troll FROM chat_settings WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"ar_enabled": bool(row[0]), "ar_text": row[1], "is_ghoul": bool(row[2]), "is_troll": bool(row[3])}
            return {"ar_enabled": False, "ar_text": "Я сейчас не могу ответить.", "is_ghoul": False, "is_troll": False}

async def update_chat_setting(chat_id: int, **kwargs):
    current = await get_chat_settings(chat_id)
    current.update(kwargs)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO chat_settings (chat_id, ar_enabled, ar_text, is_ghoul, is_troll)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                ar_enabled=excluded.ar_enabled,
                ar_text=excluded.ar_text,
                is_ghoul=excluded.is_ghoul,
                is_troll=excluded.is_troll
        """, (chat_id, int(current["ar_enabled"]), current["ar_text"], int(current["is_ghoul"]), int(current["is_troll"])))
        await db.commit()

async def add_note(chat_id: int, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO notes (chat_id, text) VALUES (?, ?)", (chat_id, text))
        await db.commit()

async def get_notes(chat_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT text FROM notes WHERE chat_id = ?", (chat_id,)) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

# ============================================================
# FSM И КЛАВИАТУРЫ
# ============================================================

class AutoResponderState(StatesGroup):
    waiting_text = State()

def main_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Автоответчик", callback_data="panel_autoresponder")],
            [InlineKeyboardButton(text="ℹ️ Помощь по командам", callback_data="panel_help")],
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

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

async def get_connection_info(connection_id: str):
    if not connection_id:
        return None
    if connection_id in business_connections:
        return business_connections[connection_id]

    try:
        connection = await bot.get_business_connection(business_connection_id=connection_id)
        business_connections[connection_id] = connection
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
# ЛОГИКА ОБРАБОТКИ
# ============================================================

async def process_command_or_autorespond(message: Message, is_owner: bool, connection_id: Optional[str] = None):
    text = (message.text or "").strip()
    chat_id = message.chat.id
    lower = text.lower()

    # 1. КОМАНДЫ УПРАВЛЕНИЯ (Только для владельца)
    if is_owner and text.startswith("."):
        if lower.startswith(".spam"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await send_reply(chat_id, "❌ Укажите текст: <code>.spam текст</code>", connection_id)
                return True
            spam_text = parts[1].strip()
            await update_chat_setting(chat_id, ar_enabled=True, ar_text=spam_text)
            await send_reply(chat_id, f"✅ <b>Автоответчик включён:</b>\n<blockquote>{spam_text}</blockquote>", connection_id)
            return True

        if lower == ".info":
            user = message.from_user
            username = f"@{user.username}" if user and user.username else "нет"
            info_text = (
                f"ℹ️ <b>Инфо о собеседнике</b>\n\n"
                f"👤 Имя: <b>{user.full_name if user else 'Неизвестно'}</b>\n"
                f"🆔 ID: <code>{user.id if user else 'N/A'}</code>\n"
                f"🔗 Username: {username}\n"
                f"💬 Chat ID: <code>{chat_id}</code>"
            )
            await send_reply(chat_id, info_text, connection_id)
            return True

        if lower == ".ghoul":
            await update_chat_setting(chat_id, is_ghoul=True)
            await send_reply(chat_id, "👻 <b>Режим Ghoul включён.</b>", connection_id)
            return True

        if lower == ".ghoulstop":
            await update_chat_setting(chat_id, is_ghoul=False)
            await send_reply(chat_id, "👻 <b>Режим Ghoul выключен.</b>", connection_id)
            return True

        if lower == ".a_troll":
            settings = await get_chat_settings(chat_id)
            new_troll_state = not settings["is_troll"]
            await update_chat_setting(chat_id, is_troll=new_troll_state)
            status_str = "включён" if new_troll_state else "выключен"
            await send_reply(chat_id, f"😈 <b>Режим Troll {status_str}.</b>", connection_id)
            return True

        if lower.startswith(".note"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                await add_note(chat_id, parts[1].strip())
                await send_reply(chat_id, "📝 <b>Заметка сохранена.</b>", connection_id)
            return True

        if lower == ".get":
            user_notes = await get_notes(chat_id)
            out = "📝 Заметок нет." if not user_notes else "📝 <b>Заметки:</b>\n\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(user_notes))
            await send_reply(chat_id, out, connection_id)
            return True

    # 2. АВТООТВЕТЫ И СПЕЦРЕЖИМЫ (На сообщения собеседника)
    if not is_owner:
        settings = await get_chat_settings(chat_id)

        if settings["ar_enabled"] and settings["ar_text"]:
            try:
                await send_reply(chat_id, settings["ar_text"], connection_id)
            except Exception:
                pass
            return True

        if settings["is_ghoul"]:
            try:
                await send_reply(chat_id, "👻 Ты написал в пустоту...", connection_id)
            except Exception:
                pass
            return True

        if settings["is_troll"]:
            troll_msgs = ["😈 Я всё вижу.", "👀 Интересно...", "🤨 Ты точно хотел это написать?", "🗿 Понял."]
            try:
                await send_reply(chat_id, random.choice(troll_msgs), connection_id)
            except Exception:
                pass
            return True

    return False

# ============================================================
# ХЭНДЛЕРЫ МЕНЮ И ПАНЕЛИ УПРАВЛЕНИЯ
# ============================================================

@dp.message(CommandStart())
async def start_command(message: Message):
    if OWNER_ID != 0 and message.from_user.id != OWNER_ID:
        await message.answer("🔒 Доступ ограничен.")
        return
    await message.answer("👻 <b>Панель управления ботом</b>", reply_markup=main_panel())

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
        "<code>.spam текст</code> — включить автоответчик с текстом\n"
        "<code>.info</code> — информация о собеседнике\n"
        "<code>.ghoul</code> — включить режим Ghoul\n"
        "<code>.ghoulstop</code> — выключить режим Ghoul\n"
        "<code>.a_troll</code> — переключить режим Troll\n"
        "<code>.note текст</code> — сохранить заметку в чате\n"
        "<code>.get</code> — показать заметки чата"
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
    settings = await get_chat_settings(chat_id)
    status = "🟢 ВКЛЮЧЕН" if settings["ar_enabled"] else "🔴 ВЫКЛЮЧЕН"
    
    text = f"🤖 <b>Автоответчик</b>\n\nСтатус: <b>{status}</b>\n\nТекст:\n<blockquote>{settings['ar_text']}</blockquote>"
    try:
        await callback.message.edit_text(text, reply_markup=autoresponder_keyboard(settings["ar_enabled"]))
    except Exception:
        pass

@dp.callback_query(F.data == "ar_change")
async def ar_change(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AutoResponderState.waiting_text)
    await callback.message.answer("✏️ <b>Введите новый текст автоответчика:</b>")

@dp.message(AutoResponderState.waiting_text)
async def ar_save_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return

    chat_id = message.chat.id
    await update_chat_setting(chat_id, ar_enabled=True, ar_text=text)
    await state.clear()
    await message.answer(
        f"✅ <b>Автоответчик включён.</b>\n\nТекст:\n<blockquote>{text}</blockquote>",
        reply_markup=autoresponder_keyboard(True)
    )

@dp.callback_query(F.data == "ar_enable")
async def ar_enable(callback: CallbackQuery):
    await callback.answer("Автоответчик включён")
    chat_id = callback.message.chat.id
    await update_chat_setting(chat_id, ar_enabled=True)
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
    await update_chat_setting(chat_id, ar_enabled=False)
    await panel_autoresponder(callback)

@dp.callback_query(F.data == "ar_disable_no")
async def ar_disable_no(callback: CallbackQuery):
    await callback.answer()
    await panel_autoresponder(callback)

# ============================================================
# ОБРАБОТКА ВСЕХ СООБЩЕНИЙ
# ============================================================

@dp.message(F.chat.type == "private")
async def private_message_handler(message: Message):
    if await dp.storage.get_state(bot=bot, key=message.chat.id):
        return

    is_owner = (OWNER_ID != 0 and message.from_user.id == OWNER_ID) or (OWNER_ID == 0)
    await process_command_or_autorespond(message, is_owner=is_owner)

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

    is_owner = (sender_id == owner_id)
    await process_command_or_autorespond(message, is_owner=is_owner, connection_id=connection_id)

# ============================================================
# ЗАПУСК И СБРОС ВЕБХУКОВ
# ============================================================

async def main():
    logging.info("Инициализация базы данных...")
    await init_db()

    logging.info("Очистка Webhook и старых подключений...")
    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    logging.info("Бот успешно запущен: @%s | ID: %s", me.username, me.id)

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
