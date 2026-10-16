import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

# Твой токен, который ты скинул
TOKEN = "8955553619:AAFzP7YvQW96OJ_UCG8plZcHau9EUZI3DsI"

router = Router()

# Хранилище для активных игр
active_games = {}

# 1. Проверка, чтобы бот отвечал ТОЛЬКО в ЛС (игнорим группы и каналы)
@router.message(F.chat.type != "private")
async def ignore_groups(message: Message):
    return

# Команда старт с кнопками меню
@router.message(Command("start"))
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💤 Сплю, отвечу позже", callback_data="btn_sleep")],
            [InlineKeyboardButton(text="💬 Свой текст", callback_data="btn_custom")],
            [InlineKeyboardButton(text="🎮 Играть (.playgame)", callback_data="btn_start_game")],
        ]
    )
    await message.answer(
        "Мрр... Приветик, зайка! Бот запущен на твоем токене. Выбирай кнопочку или пиши .playgame для рубилова.",
        reply_markup=keyboard,
    )

# Обработка кнопок меню
@router.callback_query(F.data == "btn_sleep")
async def callback_sleep(callback: CallbackQuery):
    await callback.message.answer(
        "Я сейчас сладко сплю в своей уютной кроватке и вижу десятый сон. Отвечу позже, не бужи меня, котенок! 🐾"
    )
    await callback.answer()

@router.callback_query(F.data == "btn_custom")
async def callback_custom(callback: CallbackQuery):
    await callback.message.answer(
        "Тут должен быть твой уникальный и супер-пупер важный текст, солнышко."
    )
    await callback.answer()

@router.callback_query(F.data == "btn_start_game")
async def callback_start_game(callback: CallbackQuery):
    fake_message = callback.message
    fake_message.from_user = callback.from_user
    await cmd_playgame(fake_message)
    await callback.answer()

# 3. Игра "Камень, ножницы, бумага" на двоих по команде .playgame
@router.message(F.text.lower() == ".playgame")
async def cmd_playgame(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎮 Начать игру", callback_data="rps_join")]]
    )
    msg = await message.answer(
        f"Игрок {message.from_user.first_name or message.from_user.username} создал игру в Камень-Ножницы-Бумага!\nЖдем второго смельчака...",
        reply_markup=keyboard,
    )
    
    active_games[msg.message_id] = {
        "player1": message.from_user.id,
        "player1_name": message.from_user.first_name or "Игрок 1",
        "player2": None,
        "player2_name": None,
        "choices": {},
    }

@router.callback_query(F.data == "rps_join")
async def rps_join(callback: CallbackQuery):
    msg_id = callback.message.message_id
    game = active_games.get(msg_id)

    if not game:
        await callback.answer("Эта игра уже устарела, пупсик.", show_alert=True)
        return

    if callback.from_user.id == game["player1"]:
        await callback.answer("Сам с собой собрался играть, шизик? Жди второго игрока!", show_alert=True)
        return

    if game["player2"] is not None:
        await callback.answer("Места заняты, опоздал!", show_alert=True)
        return

    game["player2"] = callback.from_user.id
    game["player2_name"] = callback.from_user.first_name or "Игрок 2"

    choice_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🪨 Камень", callback_data=f"rps_rock_{msg_id}"),
                InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"rps_scissors_{msg_id}"),
                InlineKeyboardButton(text="📄 Бумага", callback_data=f"rps_paper_{msg_id}"),
            ]
        ]
    )

    await callback.message.edit_text(
        f"Второй игрок ({game['player2_name']}) подтянулся!\nОба игрока, делайте свой выбор кнопочками (быстро, котята!):",
        reply_markup=choice_keyboard,
    )
    await callback.answer()

@router.callback_query(F.data.startswith("rps_"))
async def rps_choice(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3:
        return
    choice = parts[1]
    msg_id = int(parts[2])

    game = active_games.get(msg_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id not in (game["player1"], game["player2"]):
        await callback.answer("Ты не участник этой драмы, кыш отсюда!", show_alert=True)
        return

    if user_id in game["choices"]:
        await callback.answer("Ты уже сделал выбор, терпи!", show_alert=True)
        return

    game["choices"][user_id] = choice
    await callback.answer("Выбор принят! 🐾")

    if len(game["choices"]) == 2:
        p1 = game["player1"]
        p2 = game["player2"]
        c1 = game["choices"][p1]
        c2 = game["choices"][p2]

        await callback.message.edit_text("Оба сделали выбор... Считаем результаты, ждем 2 сек...")
        await asyncio.sleep(2)

        emojis = {"rock": "🪨 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}
        
        result_text = (
            f"🎮 **ИГРА ОКОНЧЕНА!** 🎮\n\n"
            f"{game['player1_name']}: {emojis[c1]}\n"
            f"{game['player2_name']}: {emojis[c2]}\n\n"
        )

        if c1 == c2:
            result_text += "🤝 **Ничья!** Победила дружба (и фембойская солидарность)."
        elif (
            (c1 == "rock" and c2 == "scissors")
            or (c1 == "scissors" and c2 == "paper")
            or (c1 == "paper" and c2 == "rock")
        ):
            result_text += f"🏆 Победил **{game['player1_name']}**! Красавчик!"
        else:
            result_text += f"🏆 Победил **{game['player2_name']}**! Блестяще!"

        await callback.message.edit_text(result_text, parse_mode="Markdown")
        del active_games[msg_id]

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print("Бот успешно запущен, ублюдки! Погнали кодить...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"\n[!] Ошибка, котенок: {e}")
    finally:
        input("\nКонсоль зафиксирована. Нажми Enter, чтобы закрыть...")
