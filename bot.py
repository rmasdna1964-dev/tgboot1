import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import BusinessMessage, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

# Твой токен
TOKEN = "8955553619:AAFzP7YvQW96OJ_UCG8plZcHau9EUZI3DsI"

router = Router()

# Ловим сообщения, которые приходят в ТВОЙ бизнес-аккаунт от клиентов
@router.business_message()
async def handle_business_message(message: BusinessMessage, bot: Bot):
    # Проверяем, что это личный чат (никаких групп и каналов)
    if message.chat.type != "private":
        return
    
    # Текст от клиента
    user_text = message.text or ""
    print(f"[{message.from_user.first_name}] написал в бизнес-лс: {user_text}")

    # Создаем кнопочки для автоответчика бизнес-чата
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💤 Сплю, отвечу позже", callback_data=" biz_sleep")],
            [InlineKeyboardButton(text="💬 Свой текст", callback_data="biz_custom")],
            [InlineKeyboardButton(text="🎮 Сыграть в КНБ", callback_data="biz_game")],
        ]
    )

    # Отправляем ответ клиенту от твоего имени через бизнес-соединение
    await bot.send_message(
        chat_id=message.chat.id,
        text="Мрр... Приветик, зайка! Хозяин сейчас занят или отдыхает, но Бинчик на связи. Выбирай вариант ниже:",
        reply_markup=keyboard,
        business_connection_id=message.business_connection_id
    )

# Обработка нажатий на инлайн-кнопки в бизнес-чате
@router.callback_query(F.data.startswith("biz_"))
async def process_business_callbacks(callback: CallbackQuery, bot: Bot):
    action = callback.data.split("_")[1]
    
    if action == "sleep":
        reply_text = "Я сейчас сладко сплю в своей уютной кроватке и вижу десятый сон. Отвечу позже, не бужи меня, котенок! 🐾"
    elif action == "custom":
        reply_text = "Тут должен быть твой уникальный и супер-пупер важный бизнес-текст, солнышко."
    elif action == "game":
        reply_text = "🎮 Ого, захотел развлечься? Пиши команду .playgame или жди, пока Бинчик настроит арену для рубилова!"
    else:
        reply_text = "Понял-принял, пупсик!"

    # Отправляем ответ на нажатие кнопки в тот же чат
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=reply_text,
        business_connection_id=callback.business_connection_id
    )
    await callback.answer()

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("Бизнес-бот запущен и готов прикрывать твою задницу, ублюдки! Ждем клиентов...")
    await bot.delete_webhook(drop_pending_updates=True)
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
