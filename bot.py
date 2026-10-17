import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command

# Токен твоего бота (не забудь поменять, если старый засветил!)
TOKEN = "8955553619:AAFzP7YvQW96OJ_UCG8plZcHau9EUZI3DsI"

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    # Приветствие в нашем стиле
    user_name = message.from_user.first_name
    
    # Кнопка для запуска игровой мини-аппки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎮 Зарубиться в игру", 
                web_app=WebAppInfo(url="https://твой-фронтенд-ссылка.com") # Сюда ссылку на сайт с игрой
            )
        ],
        [
            InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top_players"),
            InlineKeyboardButton(text="⚙️ Профиль", callback_data="profile")
        ]
    ])
    
    await message.answer(
        f"Здарова, **{user_name}**! Добро пожаловать в нашу пацанскую тусовку.\n\n"
        "Здесь ты можешь качать персонажа, фармить бабки, соревноваться с корешами и не париться насчет учебы. Жмай кнопку ниже и погнали!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "top_players")
async def show_top(callback):
    await callback.answer("Считаем очки...", show_alert=False)
    await callback.message.edit_text(
        "🏆 **Топ-3 бродяги на районе:**\n\n"
        "1. @Z_L_0_l — 999,999 очков\n"
        "2. Кент — 540,200 очков\n"
        "3. Ты — пока на дне, котенок 😏",
        parse_mode="Markdown"
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    print("[+] Игровой бот для пацанов запущен и пашет!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
