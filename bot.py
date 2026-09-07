import os
import time
import json
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

import aiofiles
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ==========================================
# 1. КОНФИГУРАЦИЯ И ПУТИ
# ==========================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("Ошибка: Переменная BOT_TOKEN не найдена в файле .env или окружении!")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

SETTINGS_FILE = DATA_DIR / "settings.json"
CHATS_FILE = DATA_DIR / "chats.json"
COOLDOWNS_FILE = DATA_DIR / "cooldowns.json"

DEFAULT_SETTINGS = {
    "auto_reply_enabled": False,
    "auto_reply_text": "Сейчас меня нет у телефона. Отвечу позже.",
    "auto_reply_interval": 900,
    "afk_enabled": False,
    "afk_text": ""
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# 2. JSON-ХРАНИЛИЩЕ И СЕРВИСЫ
# ==========================================
class JSONStorageService:
    def __init__(self, file_path: Path, default_data: Dict[str, Any] = None):
        self.file_path = file_path
        self.default_data = default_data if default_data is not None else {}
        self._lock = asyncio.Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.default_data, f, ensure_ascii=False, indent=4)

    async def load_data(self) -> Dict[str, Any]:
        async with self._lock:
            if not self.file_path.exists():
                return self.default_data.copy()
            try:
                async with aiofiles.open(self.file_path, mode="r", encoding="utf-8") as f:
                    content = await f.read()
                    if not content.strip():
                        return self.default_data.copy()
                    return json.loads(content)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Ошибка чтения файла {self.file_path}: {e}. Загружаем дефолтные данные.")
                return self.default_data.copy()

    async def save_data(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            temp_file = self.file_path.with_suffix(".tmp")
            try:
                async with aiofiles.open(temp_file, mode="w", encoding="utf-8") as f:
                    await f.write(json.dumps(data, ensure_ascii=False, indent=4))
                temp_file.replace(self.file_path)
            except Exception as e:
                logger.error(f"Ошибка записи в {self.file_path}: {e}")
                if temp_file.exists():
                    temp_file.unlink()

    async def get_user_data(self, user_id: int, default_user_data: Dict[str, Any]) -> Dict[str, Any]:
        data = await self.load_data()
        str_id = str(user_id)
        if str_id not in data:
            data[str_id] = default_user_data.copy()
            await self.save_data(data)
            return default_user_data.copy()
        
        updated = False
        for k, v in default_user_data.items():
            if k not in data[str_id]:
                data[str_id][k] = v
                updated = True
        if updated:
            await self.save_data(data)
            
        return data[str_id]

    async def update_user_data(self, user_id: int, key: str, value: Any, default_user_data: Dict[str, Any]) -> Dict[str, Any]:
        data = await self.load_data()
        str_id = str(user_id)
        if str_id not in data:
            data[str_id] = default_user_data.copy()
        
        data[str_id][key] = value
        await self.save_data(data)
        return data[str_id]

# Инициализация сервисов
settings_storage = JSONStorageService(SETTINGS_FILE, default_data={})
chats_storage = JSONStorageService(CHATS_FILE, default_data={})
cooldowns_storage = JSONStorageService(COOLDOWNS_FILE, default_data={})

class RateLimitService:
    @staticmethod
    async def can_send_reply(user_id: int, chat_id: int, interval_seconds: int) -> bool:
        data = await cooldowns_storage.load_data()
        last_reply = data.get(str(user_id), {}).get(str(chat_id), 0)
        return (time.time() - last_reply) >= interval_seconds

    @staticmethod
    async def update_last_reply(user_id: int, chat_id: int) -> None:
        data = await cooldowns_storage.load_data()
        u_key, c_key = str(user_id), str(chat_id)
        if u_key not in data:
            data[u_key] = {}
        data[u_key][c_key] = time.time()
        await cooldowns_storage.save_data(data)

# ==========================================
# 3. КЛАВИАТУРЫ (INLINE)
# ==========================================
def get_main_keyboard(auto_reply_enabled: bool, afk_enabled: bool) -> InlineKeyboardMarkup:
    ar_status = "🟢" if auto_reply_enabled else "🔴"
    afk_status = "🟢" if afk_enabled else "🔴"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🤖 Автоответчик: {ar_status}", callback_data="nav_autoreply"),
            InlineKeyboardButton(text=f"😴 AFK: {afk_status}", callback_data="nav_afk")
        ],
        [
            InlineKeyboardButton(text="📝 Команды", callback_data="nav_commands"),
            InlineKeyboardButton(text="📊 Статус", callback_data="nav_status")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="nav_settings"),
            InlineKeyboardButton(text="❌ Отключить всё", callback_data="nav_disable_all")
        ]
    ])

def get_autoreply_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    toggle_btn = (
        InlineKeyboardButton(text="🔴 Выключить", callback_data="ar_off")
        if enabled else
        InlineKeyboardButton(text="🟢 Включить", callback_data="ar_on")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [toggle_btn],
        [
            InlineKeyboardButton(text="📝 Изменить текст", callback_data="ar_change_text"),
            InlineKeyboardButton(text="👁 Предпросмотр", callback_data="ar_preview")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_main")]
    ])

def get_afk_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    toggle_btn = (
        InlineKeyboardButton(text="🔴 Выключить AFK", callback_data="afk_off")
        if enabled else
        InlineKeyboardButton(text="🟢 Включить AFK", callback_data="afk_on_prompt")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [toggle_btn],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_main")]
    ])

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])

def get_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 мин", callback_data="set_int_60"),
            InlineKeyboardButton(text="5 мин", callback_data="set_int_300"),
            InlineKeyboardButton(text="15 мин", callback_data="set_int_900")
        ],
        [
            InlineKeyboardButton(text="30 мин", callback_data="set_int_1800"),
            InlineKeyboardButton(text="1 час", callback_data="set_int_3600")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_main")]
    ])

def get_disable_all_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отключить", callback_data="confirm_disable_all"),
            InlineKeyboardButton(text="❌ Нет", callback_data="nav_main")
        ]
    ])

def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_main")]
    ])

# ==========================================
# 4. СОСТОЯНИЯ FSM
# ==========================================
class BotStates(StatesGroup):
    waiting_for_autoreply_text = State()
    waiting_for_afk_reason = State()

# ==========================================
# 5. ХЭНДЛЕРЫ И ЛОГИКА
# ==========================================
router = Router()
SPAM_COOLDOWN = {}

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    
    text = (
        "🤖 **Автоматизация Telegram**\n\n"
        "Здесь вы можете управлять автоответчиком,\n"
        "AFK и доступными командами.\n\n"
        f"🤖 Автоответчик: {'🟢' if settings['auto_reply_enabled'] else '🔴'}\n"
        f"😴 AFK: {'🟢' if settings['afk_enabled'] else '🔴'}"
    )
    await message.answer(text, reply_markup=get_main_keyboard(settings['auto_reply_enabled'], settings['afk_enabled']), parse_mode="Markdown")

# --- ПАНЕЛЬ И НАВИГАЦИЯ ---
@router.callback_query(F.data == "nav_main")
async def nav_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    
    text = (
        "🤖 **Автоматизация Telegram**\n\n"
        "Здесь вы можете управлять автоответчиком,\n"
        "AFK и доступными командами.\n\n"
        f"🤖 Автоответчик: {'🟢' if settings['auto_reply_enabled'] else '🔴'}\n"
        f"😴 AFK: {'🟢' if settings['afk_enabled'] else '🔴'}"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(settings['auto_reply_enabled'], settings['afk_enabled']), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "nav_autoreply")
async def nav_autoreply(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    interval_min = settings['auto_reply_interval'] // 60
    
    text = (
        "🤖 **Автоответчик**\n\n"
        f"Статус: {'🟢 Включён' if settings['auto_reply_enabled'] else '🔴 Выключен'}\n"
        f"Текст: {settings['auto_reply_text'] if settings['auto_reply_text'] else 'не установлен'}\n"
        f"Интервал: {interval_min} минут"
    )
    await callback.message.edit_text(text, reply_markup=get_autoreply_keyboard(settings['auto_reply_enabled']), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "nav_afk")
async def nav_afk(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    
    text = (
        "😴 **Управление AFK**\n\n"
        f"Статус: {'🟢 Включён' if settings['afk_enabled'] else '🔴 Выключен'}\n"
        f"Причина: {settings['afk_text'] if settings['afk_text'] else 'не указана'}"
    )
    await callback.message.edit_text(text, reply_markup=get_afk_keyboard(settings['afk_enabled']), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "nav_commands")
async def nav_commands(callback: CallbackQuery):
    text = (
        "📝 **Список доступных команд:**\n\n"
        "• `.afk [причина]` — Включить режим AFK\n"
        "• `.afk off` — Выключить режим AFK\n"
        "• `.status` — Посмотреть текущий статус систем\n"
        "• `.auto` — Переключить автоответчик\n"
        "• `.spam [текст]` — Безопасный авто-ответ\n"
        "• `.help` — Справка по командам"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "nav_status")
async def nav_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    chats_data = await chats_storage.load_data()
    user_chats = len(chats_data.get(str(user_id), []))
    
    interval_min = settings['auto_reply_interval'] // 60
    has_text = "установлен" if settings['auto_reply_text'] else "не установлен"
    
    text = (
        "📊 **Статус**\n\n"
        f"🤖 Автоответчик: {'🟢 Включён' if settings['auto_reply_enabled'] else '🔴 Выключен'}\n"
        f"😴 AFK: {'🟢 Включён' if settings['afk_enabled'] else '🔴 Выключен'}\n\n"
        f"📝 Текст: {has_text}\n"
        f"⏱ Интервал: {interval_min} минут\n\n"
        f"💬 Разрешённых чатов: {user_chats}"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "nav_settings")
async def nav_settings(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    interval_min = settings['auto_reply_interval'] // 60
    
    text = (
        "⚙️ **Настройки**\n\n"
        f"Текущий интервал автоответчика: **{interval_min} минут**\n"
        "Выберите новый интервал отправки повторных ответов:"
    )
    await callback.message.edit_text(text, reply_markup=get_settings_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("set_int_"))
async def process_set_interval(callback: CallbackQuery):
    user_id = callback.from_user.id
    seconds = int(callback.data.split("_")[2])
    await settings_storage.update_user_data(user_id, "auto_reply_interval", seconds, DEFAULT_SETTINGS)
    
    await callback.answer(f"✅ Интервал изменён на {seconds // 60} минут!")
    await nav_settings(callback)

@router.callback_query(F.data == "nav_disable_all")
async def nav_disable_all(callback: CallbackQuery):
    text = "⚠️ **Отключить все автоматизации?**\n\nАвтоответчик и AFK будут выключены."
    await callback.message.edit_text(text, reply_markup=get_disable_all_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "confirm_disable_all")
async def confirm_disable_all(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await settings_storage.update_user_data(user_id, "auto_reply_enabled", False, DEFAULT_SETTINGS)
    await settings_storage.update_user_data(user_id, "afk_enabled", False, DEFAULT_SETTINGS)
    
    await callback.answer("✅ Все автоматизации отключены!")
    await nav_main(callback, state)

# --- АВТООТВЕТЧИК УПРАВЛЕНИЕ ---
@router.callback_query(F.data == "ar_on")
async def ar_on(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    
    if not settings["auto_reply_text"]:
        await state.set_state(BotStates.waiting_for_autoreply_text)
        await callback.message.edit_text("📝 **Отправьте текст автоответчика.**", reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        await callback.answer()
        return

    await settings_storage.update_user_data(user_id, "auto_reply_enabled", True, DEFAULT_SETTINGS)
    await callback.answer("🟢 Автоответчик включён!")
    await nav_autoreply(callback)

@router.callback_query(F.data == "ar_off")
async def ar_off(callback: CallbackQuery):
    user_id = callback.from_user.id
    await settings_storage.update_user_data(user_id, "auto_reply_enabled", False, DEFAULT_SETTINGS)
    await callback.answer("🔴 Автоответчик выключен!")
    await nav_autoreply(callback)

@router.callback_query(F.data == "ar_change_text")
async def ar_change_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_autoreply_text)
    await callback.message.edit_text("📝 **Отправьте новый текст автоответчика.**", reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.message(BotStates.waiting_for_autoreply_text)
async def process_new_ar_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    new_text = message.text.strip()
    
    await settings_storage.update_user_data(user_id, "auto_reply_text", new_text, DEFAULT_SETTINGS)
    await settings_storage.update_user_data(user_id, "auto_reply_enabled", True, DEFAULT_SETTINGS)
    await state.clear()
    
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    interval_min = settings['auto_reply_interval'] // 60
    
    await message.answer("✅ **Текст успешно сохранён!**", parse_mode="Markdown")
    text = f"🤖 **Автоответчик**\n\nСтатус: 🟢 Включён\nТекст: {settings['auto_reply_text']}\nИнтервал: {interval_min} минут"
    await message.answer(text, reply_markup=get_autoreply_keyboard(True), parse_mode="Markdown")

@router.callback_query(F.data == "ar_preview")
async def ar_preview(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
    reply_text = settings['auto_reply_text'] if settings['auto_reply_text'] else "_(Текст не установлен)_"
    await callback.message.answer(f"👁 **Предпросмотр автоответа:**\n\n{reply_text}", parse_mode="Markdown")
    await callback.answer()

# --- AFK УПРАВЛЕНИЕ ---
@router.callback_query(F.data == "afk_on_prompt")
async def afk_on_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_afk_reason)
    await callback.message.edit_text("😴 **Отправьте причину ухода в AFK:**", reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.message(BotStates.waiting_for_afk_reason)
async def process_afk_reason(message: Message, state: FSMContext):
    user_id = message.from_user.id
    reason = message.text.strip()
    
    await settings_storage.update_user_data(user_id, "afk_enabled", True, DEFAULT_SETTINGS)
    await settings_storage.update_user_data(user_id, "afk_text", reason, DEFAULT_SETTINGS)
    await state.clear()
    
    await message.answer(f"😴 **AFK включён**\n\nПричина:\n{reason}", parse_mode="Markdown")
    text = f"😴 **Управление AFK**\n\nСтатус: 🟢 Включён\nПричина: {reason}"
    await message.answer(text, reply_markup=get_afk_keyboard(True), parse_mode="Markdown")

@router.callback_query(F.data == "afk_off")
async def afk_off(callback: CallbackQuery):
    user_id = callback.from_user.id
    await settings_storage.update_user_data(user_id, "afk_enabled", False, DEFAULT_SETTINGS)
    await settings_storage.update_user_data(user_id, "afk_text", "", DEFAULT_SETTINGS)
    await callback.answer("🔴 AFK выключен!")
    await nav_afk(callback)

@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await nav_main(callback, state)
    await callback.answer("Действие отменено.")

# --- КОМАНДЫ (.) И ОБРАБОТЧИК СООБЩЕНИЙ ---
@router.message(F.text.startswith("."))
async def handle_dot_commands(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text.startswith(".afk"):
        args = text[4:].strip()
        if args.lower() == "off":
            await settings_storage.update_user_data(user_id, "afk_enabled", False, DEFAULT_SETTINGS)
            await settings_storage.update_user_data(user_id, "afk_text", "", DEFAULT_SETTINGS)
            await message.reply("🔴 AFK выключен!")
        else:
            reason = args if args else "Занят"
            await settings_storage.update_user_data(user_id, "afk_enabled", True, DEFAULT_SETTINGS)
            await settings_storage.update_user_data(user_id, "afk_text", reason, DEFAULT_SETTINGS)
            await message.reply(f"😴 **AFK включён**\n\nПричина:\n{reason}", parse_mode="Markdown")

    elif text == ".status":
        settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
        chats_data = await chats_storage.load_data()
        user_chats = len(chats_data.get(str(user_id), []))
        interval_min = settings['auto_reply_interval'] // 60

        reply = (
            "📊 **Текущий статус:**\n\n"
            f"🤖 Автоответчик: {'🟢 Включён' if settings['auto_reply_enabled'] else '🔴 Выключен'}\n"
            f"😴 AFK: {'🟢 Включён' if settings['afk_enabled'] else '🔴 Выключен'}\n"
            f"⏱ Интервал: {interval_min} мин\n"
            f"💬 Чат-лист: {user_chats} чатов"
        )
        await message.reply(reply, parse_mode="Markdown")

    elif text == ".auto":
        settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)
        new_state = not settings["auto_reply_enabled"]
        await settings_storage.update_user_data(user_id, "auto_reply_enabled", new_state, DEFAULT_SETTINGS)
        status_str = "🟢 Включён" if new_state else "🔴 Выключен"
        await message.reply(f"🤖 Автоответчик теперь: **{status_str}**", parse_mode="Markdown")

    elif text.startswith(".spam"):
        spam_text = text[5:].strip()
        if not spam_text:
            await message.reply("⚠️ Укажите текст: `.spam Ваш текст`", parse_mode="Markdown")
            return

        now = time.time()
        if now - SPAM_COOLDOWN.get(user_id, 0) < 5.0:
            await message.reply("🛡 **Защита от спама:** Не чаще раза в 5 секунд.")
            return

        chats_data = await chats_storage.load_data()
        allowed_chats = chats_data.get(str(user_id), [])
        if message.chat.id not in allowed_chats:
            await message.reply("🛡 **Безопасность:** Чат не входит в список разрешённых.")
            return

        SPAM_COOLDOWN[user_id] = now
        await message.reply(f"💬 [Безопасный авто-ответ]: {spam_text}")

    elif text == ".help":
        help_msg = (
            "📖 **Справка по точка-командам:**\n\n"
            "• `.afk [причина]` — Включить AFK\n"
            "• `.afk off` — Выключить AFK\n"
            "• `.status` — Статус систем\n"
            "• `.auto` — Переключить автоответчик\n"
            "• `.spam [текст]` — Безопасный авто-ответ\n"
            "• `.help` — Вывести эту справку"
        )
        await message.reply(help_msg, parse_mode="Markdown")

@router.business_message()
@router.message(F.chat.type == "private")
async def handle_incoming_messages(message: Message):
    if message.text and message.text.startswith("."):
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    conn_id = message.business_connection_id

    # Авто-регистрация чата
    chats_data = await chats_storage.load_data()
    str_uid = str(user_id)
    if str_uid not in chats_data:
        chats_data[str_uid] = []
    if chat_id not in chats_data[str_uid]:
        chats_data[str_uid].append(chat_id)
        await chats_storage.save_data(chats_data)

    settings = await settings_storage.get_user_data(user_id, DEFAULT_SETTINGS)

    # AFK
    if settings["afk_enabled"] and settings["afk_text"]:
        if await RateLimitService.can_send_reply(user_id, chat_id, interval_seconds=60):
            await RateLimitService.update_last_reply(user_id, chat_id)
            afk_msg = f"😴 Пользователь сейчас AFK.\n\nПричина: {settings['afk_text']}"
            await message.bot.send_message(chat_id=chat_id, text=afk_msg, business_connection_id=conn_id)
            return

    # Автоответчик
    if settings["auto_reply_enabled"] and settings["auto_reply_text"]:
        interval = settings["auto_reply_interval"]
        if await RateLimitService.can_send_reply(user_id, chat_id, interval_seconds=interval):
            await RateLimitService.update_last_reply(user_id, chat_id)
            await message.bot.send_message(chat_id=chat_id, text=settings["auto_reply_text"], business_connection_id=conn_id)

# ==========================================
# 6. ЗАПУСК БОТА
# ==========================================
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот успешно запущен!")
    
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
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
