import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import BusinessMessage

# Твой токен
TOKEN = "8955553619:AAFzP7YvQW96OJ_UCG8plZcHau9EUZI3DsI"

router = Router()

# Ловим сообщения, которые приходят в ТВОЙ бизнес-аккаунт от клиентов в ЛС
@router.business_message()
async def handle_business_message(message: BusinessMessage, bot: Bot):
    # На всякий случай проверяем, что это точно личный чат (а не группа бизнес-аккаунта)
    if message.chat.type != "private":
        return
    
    # Текст, который написал клиент
    user_text = message.text or ""
    print(f"[{message.from_user.first_name}] написал в бизнес-лс: {user_text}")

    # Здесь твоя логика автоответчика! 
    # Например, если ты занят или спишь:
    auto_reply = (
        "Мрр... Приветик! Сейчас Бинчик за главного, а хозяин занят или спит. "
        "Передам ему твое сообщение в ближайшее время, котенок! 🐾"
    )

    # Отправляем ответ в тот же чат через бизнес-соединение
    await bot.send_message(
        chat_id=message.chat.id,
        text=auto_reply,
        business_connection_id=message.business_connection_id
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("Бизнес-автоответчик запущен, ублюдки! Ждем клиентов...")
    # Очищаем старые апдейты и запускаем поллинг
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
