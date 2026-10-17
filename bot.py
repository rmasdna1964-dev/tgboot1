import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# Твой токен (береги его, не свети больше, зайка!)
TOKEN = "8955553619:AAFzP7YvQW96OJ_UCG8plZcHau9EUZI3DsI"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище данных игроков в памяти (в реале можно прикрутить SQLite)
players = {}

def get_profile_text(user_id, user_name):
    p = players[user_id]
    return (
        f"👤 **Бродяга:** {user_name}\n"
        f"💪 Сила: **{p['strength']}**\n"
        f"💰 Бабло: **{p['money']}** руб.\n"
        f"⚡ Энергия: **{p['energy']}**/100\n\n"
        f"Выбирай действие, котенок:"
    )

def get_game_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏋️ Качать бицуху (+Сила)", callback_data="train"),
            InlineKeyboardButton(text="🛒 Работать (+Бабло)", callback_data="work")
        ],
        [
            InlineKeyboardButton(text="⚡ Отдохнуть", callback_data="rest"),
            InlineKeyboardButton(text="🥊 Уличный бой", callback_data="fight")
        ]
    ])

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if user_id not in players:
        players[user_id] = {
            "strength": 10,
            "money": 100,
            "energy": 100
        }
    
    await message.answer(
        f"Здарова, **{user_name}**! Добро халовать в нашу чисто пацанскую игру прямо в чате.\n\n" +
        get_profile_text(user_id, user_name),
        reply_markup=get_game_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.in_({"train", "work", "rest", "fight"}))
async def process_game_action(callback):
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    
    if user_id not in players:
        players[user_id] = {"strength": 10, "money": 100, "energy": 100}
    
    p = players[user_id]
    action = callback.data
    
    if action == "train":
        if p["energy"] >= 15:
            p["energy"] -= 15
            p["strength"] += 2
            await callback.answer("Ты знатно попотев в качалке! +2 к силе 💪", show_alert=False)
        else:
            await callback.answer("Энергия на нуле, братишка! Иди отдохни.", show_alert=True)
            
    elif action == "work":
        if p["energy"] >= 20:
            p["energy"] -= 20
            earned = p["strength"] * 5
            p["money"] += earned
            await callback.answer(f"Заработал на теме {earned} рублей! 💵", show_alert=False)
        else:
            await callback.answer("Устал как собака, нужна энергия!", show_alert=True)
            
    elif action == "rest":
        p["energy"] = 100
        await callback.answer("Поспал, попил липтона, силы восстановлены! 🧃", show_alert=False)
        
    elif action == "fight":
        if p["energy"] >= 30:
            p["energy"] -= 30
            if p["strength"] >= 15:
                p["money"] += 150
                await callback.answer("Раскидал чушпанов на районе! +150 руб 🥊😎", show_alert=True)
            else:
                await callback.answer("Слабоват еще, люлей отхватил... Качай силу!", show_alert=True)
        else:
            await callback.answer("Сил нет даже кулак сжать, отдохни!", show_alert=True)

    # Обновляем сообщение с новым состоянием игрока
    await callback.message.edit_text(
        get_profile_text(user_id, user_name),
        reply_markup=get_game_keyboard(),
        parse_mode="Markdown"
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    print("[+] Внутриигровой Telegram-бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
