import asyncio
import logging
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

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "8955553619:AAGPRoVXir741kBwfYcGg6GlJhI4WzezK2Y").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояние активных спам-процессов: {chat_id: bool}
active_spams = {}

class SpamState(StatesGroup):
    waiting_for_target = State()
    waiting_for_text = State()
    confirm_spam = State()

# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def get_main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить спам", callback_data="start_spam_flow")],
            [InlineKeyboardButton(text="🛑 Остановить текущий спам", callback_data="stop_spam")],
            [InlineKeyboardButton(text="📖 Инструкция", callback_data="show_instruction")]
        ]
    )

def get_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Пуск", callback_data="confirm_start"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data="cancel_spam")
            ]
        ]
    )

def get_cancel_only_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_spam")]
        ]
    )

# ============================================================
# ОБРАБОТКА МЕНЮ И FSM
# ============================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 **Главное меню управления**\n\nВыбери нужное действие ниже:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "show_instruction")
async def show_instruction(callback: CallbackQuery):
    text = (
        "📖 **Инструкция по настройке и работе:**\n\n"
        "1️⃣ **Telegram Business (Подключение к ЛС):**\n"
        "• Открой Настройки Telegram ➔ **Telegram для бизнеса**.\n"
        "• Перейди в раздел **Чат-боты** и добавь этого бота.\n"
        "• Выбери «Все чаты», чтобы бот мог отправлять сообщения от твоего имени.\n\n"
        "2️⃣ **Запуск спама из меню:**\n"
        "• Нажми кнопку **«🚀 Запустить спам»**.\n"
        "• Введи `@username` или `ID` цели.\n"
        "• Введи текст сообщения.\n"
        "• Подтверди запуск кнопкой **«✅ Пуск»**.\n\n"
        "3️⃣ **Остановка:**\n"
        "• В любой момент нажми **«🛑 Остановить текущий спам»**."
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "start_spam_flow")
async def start_spam_flow(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SpamState.waiting_for_target)
    await callback.message.edit_text(
        "👤 **Шаг 1 из 2:**\nВведи **Username** (например `@username`) или **ID** человека, которому нужно отправлять сообщения:",
        reply_markup=get_cancel_only_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(SpamState.waiting_for_target)
async def process_target(message: Message, state: FSMContext):
    target = message.text.strip()
    await state.update_data(target=target)
    await state.set_state(SpamState.waiting_for_text)
    await message.answer(
        f"💬 **Шаг 2 из 2:**\nЦель: `{target}`\n\nТеперь напиши **текст сообщения** для спама:",
        reply_markup=get_cancel_only_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(SpamState.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    spam_text = message.text.strip()
    await state.update_data(spam_text=spam_text)
    
    data = await state.get_data()
    target = data.get("target")
    
    await state.set_state(SpamState.confirm_spam)
    await message.answer(
        f"⚙️ **Подтверждение запуска:**\n\n"
        f"🎯 **Цель:** `{target}`\n"
        f"📝 **Текст:** {spam_text}\n\n"
        f"Нажми **«Пуск»** для начала или **«Отклонить»** для отмены.",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "confirm_start", SpamState.confirm_spam)
async def confirm_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target = data.get("target")
    spam_text = data.get("spam_text")
    await state.clear()

    chat_id = callback.message.chat.id
    active_spams[chat_id] = True

    await callback.message.edit_text(
        f"🚀 **Спам запущен!**\nЦель: `{target}`\n\nДля остановки нажми кнопку ниже.",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

    # Запуск цикла спама
    for _ in range(50):
        if not active_spams.get(chat_id, False):
            break
        try:
            await bot.send_message(chat_id=target, text=spam_text)
            await asyncio.sleep(0.2)
        except Exception as e:
            await callback.message.answer(f"❌ Ошибка отправки на `{target}`: {e}")
            break

    active_spams[chat_id] = False

@dp.callback_query(F.data == "cancel_spam")
async def cancel_spam(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ **Операция отменена.**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    await callback.answer("Отменено")

@dp.callback_query(F.data == "stop_spam")
async def stop_spam(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    active_spams[chat_id] = False
    await callback.message.answer("🛑 **Запрос на остановку отправлен.**")
    await callback.answer()

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
