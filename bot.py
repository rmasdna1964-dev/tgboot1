import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command

# Токен твоего бота (получай у BotFather)
TOKEN = "8955553619:AAFzP7YvQW96OJ_UCG8plZcHau9EUZI3DsI"

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    # Кнопка для запуска нашего Mini App с «нарисованными» звездами
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⭐ Открыть кошелек со Звёздами", 
                web_app=WebAppInfo(url="https:// твой-сайт-или-фронтенд .com")
            )
        ]
    ])
    
    await message.answer(
        "Привет, зайка! Запусти мини-приложение, чтобы увидеть свой «надежный» баланс звезд.",
        reply_markup=keyboard
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    print("[+] Бот запущен, солнце. Ждем жертв... то есть пользователей.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
