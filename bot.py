import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from supabase import Client, create_client

# Настройки и ключи
BOT_TOKEN = "8872260684:AAGCK3Tpex8I3p8rAtWwR9_HFpNpwvTFgrE"
SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"

# Инициализация Supabase и бота
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Флаг для управления состоянием спама
is_spamming = False


async def get_or_create_user(user_id: int, username: str):
    response = (
        supabase.table("profiles").select("*").eq("id", user_id).execute()
    )

    if not response.data:
        new_user = {"id": user_id, "username": username, "balance": 100}
        data = supabase.table("profiles").insert(new_user).execute()
        return data.data[0], True

    return response.data[0], False


# Клавиатура главного меню
def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 Инструкция", callback_data="help_info")
    builder.button(text="💰 Мой баланс", callback_data="check_balance")
    builder.adjust(1)
    return builder.as_markup()


# Клавиатура для возврата назад
def get_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В главное меню", callback_data="main_menu")
    return builder.as_markup()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Аноним"

    user_data, is_created = await get_or_create_user(user_id, username)

    if is_created:
        text = (
            f"⚡ **ДОБРО ПОЖАЛОВАТЬ В BAZOOKA BOT, {username.upper()}!** ⚡\n\n"
            f"🎉 Вы успешно зарегистрированы!\n"
            f"🎁 Вам начислен стартовый бонус: **{user_data['balance']} монет**.\n\n"
            f"Используйте кнопки ниже для навигации:"
        )
    else:
        text = (
            f"🔥 **С ВОЗВРАЩЕНИЕМ, {username.upper()}!** 🔥\n\n"
            f"Готовы шуметь? Все системы работают штатно.\n"
            f"Нажмите **Инструкция**, чтобы вспомнить команды."
        )

    await message.answer(
        text, reply_markup=get_main_keyboard(), parse_mode="Markdown"
    )


# Обработчик кнопки "Инструкция"
@dp.callback_query(F.data == "help_info")
async def process_help(callback: CallbackQuery):
    help_text = (
        "📜 **ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ**\n\n"
        "🟢 `.spam <текст>` — Обычный спам с задержкой 1.5 сек.\n"
        "🔥 `.killerspam <текст>` — Турбо-спам без задержек (максимальная скорость).\n"
        "🛑 `.stop` — Мгновенно остановить любой спам.\n\n"
        "⚠️ *Внимание: Будьте аккуратны с быстрой рассылкой, Telegram может выдать временный флуд-блок.*"
    )
    await callback.message.edit_text(
        help_text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await callback.answer()


# Обработчик кнопки "Мой баланс"
@dp.callback_query(F.data == "check_balance")
async def process_balance(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or "Аноним"
    user_data, _ = await get_or_create_user(user_id, username)

    balance_text = (
        f"💳 **ВАШ ПРОФИЛЬ**\n\n"
        f"👤 Пользователь: @{username}\n"
        f"💰 Баланс: **{user_data['balance']} монет**"
    )
    await callback.message.edit_text(
        balance_text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
    )
    await callback.answer()


# Обработчик кнопки "В главное меню"
@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: CallbackQuery):
    username = callback.from_user.username or "Аноним"
    text = (
        f"🔥 **ГЛАВНОЕ МЕНЮ**\n\n"
        f"Выберите нужное действие с помощью кнопок ниже:"
    )
    await callback.message.edit_text(
        text, reply_markup=get_main_keyboard(), parse_mode="Markdown"
    )
    await callback.answer()


# Обычный спам
@dp.message(lambda msg: msg.text and msg.text.startswith(".spam"))
async def cmd_spam(message: Message):
    global is_spamming
    text_to_send = message.text[5:].strip()

    if not text_to_send:
        await message.answer(
            "Использование: `.spam Ваш текст`", parse_mode="Markdown"
        )
        return

    is_spamming = True
    await message.answer(
        "🚀 **Обычный спам запущен** (задержка 1.5 сек).\nОстановить: `.stop`",
        parse_mode="Markdown",
    )

    while is_spamming:
        try:
            await message.answer(text_to_send)
            await asyncio.sleep(1.5)
        except Exception as e:
            logging.error(f"Ошибка при отправке: {e}")
            await asyncio.sleep(2)


# Быстрый спам
@dp.message(lambda msg: msg.text and msg.text.startswith(".killerspam"))
async def cmd_killer_spam(message: Message):
    global is_spamming
    text_to_send = message.text[11:].strip()

    if not text_to_send:
        await message.answer(
            "Использование: `.killerspam Ваш текст`", parse_mode="Markdown"
        )
        return

    is_spamming = True
    await message.answer(
        "⚡ **KILLER SPAM запущен!**\nОстановить: `.stop`",
        parse_mode="Markdown",
    )

    while is_spamming:
        try:
            await message.answer(text_to_send)
            await asyncio.sleep(0.01)
        except Exception:
            await asyncio.sleep(1)


# Команда остановки
@dp.message(lambda msg: msg.text == ".stop")
async def cmd_stop(message: Message):
    global is_spamming
    is_spamming = False
    await message.answer("🛑 Спам остановлен.")


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
