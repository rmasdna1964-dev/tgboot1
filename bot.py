import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client, Client

# Настройки и ключи
BOT_TOKEN = "YOUR_BOT_TOKEN"
SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"

PREMIUM_PRICE_STARS = 10

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Словари состояний
active_trolls = {}    # chat_id: bool
premium_users = set()  # set of user_id

# Состояние AFK (автоответчика)
afk_status = {"active": False, "reason": "Занят"}

class AFKState(StatesGroup):
    waiting_for_text = State()

active_games = {}

RPS_NAMES = {
    "rock": "🗿 Камень",
    "scissors": "✂️ Ножницы",
    "paper": "📄 Бумага"
}

TROLL_PHRASES = [
    "Спорить с тобой — это как играть в шахматы с голубем.",
    "Ты всегда такой умный или сегодня особенный день?",
    "Ага, очень интересно, продолжай (нет).",
    "Мнение принято, отправлено в корзину."
]

async def get_or_create_user(user_id: int, username: str):
    try:
        response = supabase.table("profiles").select("*").eq("id", user_id).execute()
        if not response.data:
            new_user = {"id": user_id, "username": username, "balance": 100}
            data = supabase.table("profiles").insert(new_user).execute()
            return data.data[0], True
        return response.data[0], False
    except Exception as e:
        logging.error(f"Ошибка БД: {e}")
        return None, False

async def send_premium_invoice(user_id: int):
    prices = [LabeledPrice(label="Премиум Доступ ко всем командам", amount=PREMIUM_PRICE_STARS)]
    await bot.send_invoice(
        chat_id=user_id,
        title="⭐ Премиум Доступ",
        description="Разблокировка эксклюзивных функций бота",
        payload="premium_access",
        provider_token="",
        currency="XTR",
        prices=prices
    )

# --- КЛАВИАТУРЫ ---

def get_main_keyboard():
    afk_btn_text = "🔴 Отключить автоответчик" if afk_status["active"] else "💤 Включить автоответчик"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=afk_btn_text, callback_data="toggle_afk_panel")],
        [
            InlineKeyboardButton(text="📖 Инструкция", callback_data="show_help"),
            InlineKeyboardButton(text="🎮 Игра", callback_data="show_game_info")
        ]
    ])

def get_help_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🆓 Бесплатные команды", callback_data="show_free_commands"),
            InlineKeyboardButton(text="⭐ Платные функции (Stars)", callback_data="show_paid_commands")
        ]
    ])

def get_paid_commands_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить Премиум (10 Stars)", callback_data="buy_premium_stars")],
        [InlineKeyboardButton(text="⬅️ Назад в меню инструкций", callback_data="show_help")]
    ])

def get_back_to_help_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню инструкций", callback_data="show_help")]
    ])

def get_confirm_turnoff_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отключить", callback_data="confirm_afk_off"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="cancel_afk_off")
        ]
    ])

def get_rps_keyboard(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗿 Камень", callback_data=f"rps_rock_{chat_id}"),
            InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"rps_scissors_{chat_id}"),
            InlineKeyboardButton(text="📄 Бумага", callback_data=f"rps_paper_{chat_id}")
        ]
    ])

def get_post_game_keyboard(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 Сыграть ещё раз", callback_data=f"rps_restart_{chat_id}"),
            InlineKeyboardButton(text="❌ Не хочу играть", callback_data=f"rps_cancel_{chat_id}")
        ]
    ])

# --- ОБРАБОТКА ОПЛАТЫ TELEGRAM STARS ---

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    user_id = message.from_user.id
    if message.successful_payment.invoice_payload == "premium_access":
        premium_users.add(user_id)
        await message.answer(
            "🎉 **Премиум доступ успешно активирован!**\n\n"
            "Вам разблокированы все платные функции.",
            parse_mode="Markdown"
        )

# --- КОМАНДА /start И ПАНЕЛЬ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "Аноним"
    await get_or_create_user(user_id, username)
    
    status_text = f"Статус автоответчика: **{'ВКЛЮЧЕН 🟢' if afk_status['active'] else 'ВЫКЛЮЧЕН 🔴'}**"
    if afk_status["active"]:
        status_text += f"\nТекущий текст: _{afk_status['reason']}_"

    text = f"Привет, {username}!\nПанель управления Telegram Business.\n\n{status_text}"
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "toggle_afk_panel")
async def process_afk_toggle_click(callback_query: CallbackQuery, state: FSMContext):
    if not afk_status["active"]:
        await state.set_state(AFKState.waiting_for_text)
        await callback_query.message.answer("⌨️ **Напишите текст для автоответчика:**", parse_mode="Markdown")
        await callback_query.answer()
    else:
        await callback_query.message.answer(
            "⚠️ **Точно отключить автоответчик?**",
            reply_markup=get_confirm_turnoff_keyboard(),
            parse_mode="Markdown"
        )
        await callback_query.answer()

@dp.message(AFKState.waiting_for_text)
async def process_afk_text_input(message: Message, state: FSMContext):
    text = message.text.strip()
    afk_status["active"] = True
    afk_status["reason"] = text
    await state.clear()
    
    await message.answer(
        f"✅ **Автоответчик успешно включен!**\n\nТекст ответа:\n_{text}_",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "confirm_afk_off")
async def process_confirm_afk_off(callback_query: CallbackQuery):
    afk_status["active"] = False
    await callback_query.message.edit_text("☀️ **Автоответчик выключен.**", parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "cancel_afk_off")
async def process_cancel_afk_off(callback_query: CallbackQuery):
    await callback_query.message.edit_text("👍 Автоответчик остался **включенным**.", parse_mode="Markdown")
    await callback_query.answer()

# --- CALLBACKS ИНСТРУКЦИИ И ОПЛАТЫ ---

@dp.callback_query(F.data == "show_help")
async def process_help_callback(callback_query: CallbackQuery):
    await callback_query.message.edit_text("📖 **Выберите категорию команд:**", reply_markup=get_help_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "show_free_commands")
async def process_free_commands_callback(callback_query: CallbackQuery):
    free_text = (
        "🆓 **Доступные команды:**\n\n"
        "👤 `.info` — Информация о пользователе\n"
        "🎮 `.starts` — Запуск игры «Камень, ножницы, бумага»"
    )
    await callback_query.message.edit_text(free_text, reply_markup=get_back_to_help_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "show_paid_commands")
async def process_paid_commands_callback(callback_query: CallbackQuery):
    paid_text = (
        "⭐ **Платные Премиум-функции:**\n"
        f"_(Стоимость доступа: **{PREMIUM_PRICE_STARS} Stars**)_\n\n"
        "🎭 `.a_troll` — Режим авто-ответа случайными фразами"
    )
    await callback_query.message.edit_text(paid_text, reply_markup=get_paid_commands_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "buy_premium_stars")
async def process_buy_premium_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id in premium_users:
        await callback_query.answer("У вас уже активирован Премиум!", show_alert=True)
        return
    await send_premium_invoice(user_id)
    await callback_query.answer("Счет отправлен в ЛС!")

# --- ЛОГИКА ИГРЫ КАМЕНЬ-НОЖНИЦЫ-БУМАГА ---

@dp.callback_query(lambda c: c.data and (c.data.startswith("rps_restart_") or c.data.startswith("rps_cancel_")))
async def process_post_game_actions(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    action, chat_id = parts[1], int(parts[2])

    if action == "restart":
        active_games[chat_id] = {"choices": {}}
        await callback_query.message.edit_text(
            "🎮 **Дуэль: Камень, ножницы, бумага!**\n\n⏳ Ожидание игроков...\n📊 Проголосовало: **0/2**",
            reply_markup=get_rps_keyboard(chat_id),
            parse_mode="Markdown"
        )
    elif action == "cancel":
        active_games.pop(chat_id, None)
        try:
            await callback_query.message.delete()
        except Exception:
            await callback_query.message.edit_text("❌ Игра завершена.")

@dp.callback_query(lambda c: c.data and c.data.startswith("rps_"))
async def process_rps_choice(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    choice, chat_id = parts[1], int(parts[2])
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name

    if chat_id not in active_games:
        await callback_query.answer("Игра не найдена. Введите .starts", show_alert=True)
        return

    game = active_games[chat_id]
    if user_id in game["choices"]:
        await callback_query.answer("Вы уже сделали выбор!", show_alert=True)
        return

    game["choices"][user_id] = {"choice": choice, "name": user_name}
    await callback_query.answer(f"Вы выбрали: {RPS_NAMES.get(choice, choice)}!")

    if len(game["choices"]) == 1:
        text = (
            f"🎮 **Дуэль: Камень, ножницы, бумага!**\n\n"
            f"👤 **{user_name}** сделал свой выбор!\n"
            f"📊 Проголосовало: **1/2**"
        )
        await callback_query.message.edit_text(text, reply_markup=get_rps_keyboard(chat_id), parse_mode="Markdown")

    elif len(game["choices"]) >= 2:
        players = list(game["choices"].values())
        p1, p2 = players[0], players[1]
        c1, c2 = p1["choice"], p2["choice"]

        if c1 == c2:
            result = "🤝 **Ничья!**"
        elif (c1 == "rock" and c2 == "scissors") or (c1 == "scissors" and c2 == "paper") or (c1 == "paper" and c2 == "rock"):
            result = f"🏆 Победил **{p1['name']}**!"
        else:
            result = f"🏆 Победил **{p2['name']}**!"

        res_text = (
            f"🎮 **Результаты:**\n\n"
            f"👤 **{p1['name']}**: {RPS_NAMES.get(c1)}\n"
            f"👤 **{p2['name']}**: {RPS_NAMES.get(c2)}\n\n"
            f"{result}"
        )
        await callback_query.message.edit_text(res_text, reply_markup=get_post_game_keyboard(chat_id), parse_mode="Markdown")

# --- ОБРАБОТЧИК TELEGRAM BUSINESS ---

@dp.business_message()
async def handle_business_message(message: Message):
    global active_trolls, active_games, afk_status
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = (message.text or "").strip()
    
    conn_id = message.business_connection_id
    if not conn_id:
        return

    # Проверка автора: is_me (вы), is_partner (собеседник)
    is_me = (user_id != chat_id)
    is_partner = (user_id == chat_id)

    # 1. Действия и команды ВЛАДЕЛЬЦА (вы)
    if is_me:
        if text.startswith("."):
            if text == ".info":
                user = message.from_user
                info_msg = (
                    f"👤 **Ваша информация:**\n\n"
                    f"• **Имя:** {user.first_name}\n"
                    f"• **ID:** `{user.id}`"
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=info_msg,
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text == ".a_troll":
                current_status = active_trolls.get(chat_id, False)
                active_trolls[chat_id] = not current_status
                status_text = "включен 🎭" if active_trolls[chat_id] else "выключен 🛑"
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Режим авто-ответов **{status_text}**",
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

    # 2. Действия и команды СОБЕСЕДНИКА
    if is_partner:
        # Автоответчик AFK
        if afk_status["active"] and message.chat.type == "private":
            await bot.send_message(
                chat_id=chat_id,
                text=afk_status["reason"],
                business_connection_id=conn_id
            )

        # Авто-ответы из списка TROLL_PHRASES
        if active_trolls.get(chat_id, False):
            await bot.send_message(
                chat_id=chat_id,
                text=random.choice(TROLL_PHRASES),
                business_connection_id=conn_id
            )

        if text.startswith("."):
            if text == ".info":
                user = message.from_user
                info_msg = (
                    f"👤 **Информация о собеседнике:**\n\n"
                    f"• **Имя:** {user.first_name}\n"
                    f"• **ID:** `{user.id}`\n"
                    f"• **Премиум:** {'Да' if user_id in premium_users else 'Нет'}"
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=info_msg,
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text == ".starts":
                active_games[chat_id] = {"choices": {}}
                await bot.send_message(
                    chat_id=chat_id,
                    text="🎮 **Дуэль: Камень, ножницы, бумага!**\n\n⏳ Ожидание игроков...",
                    reply_markup=get_rps_keyboard(chat_id),
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text == ".a_troll":
                if user_id not in premium_users:
                    await send_premium_invoice(user_id)
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"⭐ **Команда доступна только Премиум-пользователям!**\nСчет ({PREMIUM_PRICE_STARS} Stars) отправлен в ЛС.",
                        business_connection_id=conn_id
                    )
                    return

                current_status = active_trolls.get(chat_id, False)
                active_trolls[chat_id] = not current_status
                status_text = "включен 🎭" if active_trolls[chat_id] else "выключен 🛑"
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Режим авто-ответов **{status_text}**",
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
