import asyncio
import logging
import random
import aiohttp
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
BOT_TOKEN = "8872260684:AAHEhMfCuLTfG0RK1kjmqUmDS-TXRiQUWzk"
SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"

# Стоимость полного Премиум-доступа (10 Telegram Stars)
PREMIUM_PRICE_STARS = 10

# Инициализация Supabase, бота и диспетчера
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Изолированные словари состояний (по chat_id)
active_spams = {}    # chat_id: bool
active_trolls = {}   # chat_id: bool
active_ghouls = {}   # chat_id: bool

# Хранилище ID пользователей с активным Премиумом
premium_users = set()

# Состояние AFK (автоответчика)
afk_status = {"active": False, "reason": "Занят"}

class AFKState(StatesGroup):
    waiting_for_text = State()

notes = {}
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
    "Мнение принято, отправлено в корзину.",
    "1000-7, гуль, получается?"
]

# Вспомогательная регистрация пользователя в Supabase
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

# Функция отправки счета на оплату Звёздами
async def send_premium_invoice(user_id: int):
    prices = [LabeledPrice(label="Премиум Доступ ко всем командам", amount=PREMIUM_PRICE_STARS)]
    
    await bot.send_invoice(
        chat_id=user_id,
        title="⭐ Премиум Доступ",
        description="Разблокировка всех платных функций (.spam, .killerspam, .send)",
        payload="premium_access",
        provider_token="",  # Для Telegram Stars оставляем пустым
        currency="XTR",     # Код валюты Telegram Stars
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
    payload = message.successful_payment.invoice_payload

    if payload == "premium_access":
        premium_users.add(user_id)
        await message.answer(
            "🎉 **Премиум доступ успешно активирован!**\n\n"
            "Вам разблокированы все платные команды:\n"
            "• `.spam [текст]`\n"
            "• `.killerspam [текст]`\n"
            "• `.send [сумма]`",
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
        await callback_query.message.answer("⌨️ **Напишите текст для автоответчика:**\n_(Этот текст будет отправляться всем в ЛС)_", parse_mode="Markdown")
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
    await callback_query.answer("Автоответчик выключен!")

@dp.callback_query(F.data == "cancel_afk_off")
async def process_cancel_afk_off(callback_query: CallbackQuery):
    await callback_query.message.edit_text("👍 Автоответчик остался **включенным**.", parse_mode="Markdown")
    await callback_query.answer()

# --- CALLBACKS ИНСТРУКЦИИ И ИГРЫ ---

@dp.callback_query(F.data == "show_help")
async def process_help_callback(callback_query: CallbackQuery):
    help_text = "📖 **Выберите категорию команд для просмотра:**"
    await callback_query.message.edit_text(help_text, reply_markup=get_help_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "show_free_commands")
async def process_free_commands_callback(callback_query: CallbackQuery):
    free_text = (
        "🆓 **Бесплатные команды:**\n\n"
        "🐱 `.cat` — Случайное фото котика.\n"
        "⚡ `.ghoul` — Цикл 1000-7 (Dead Inside).\n"
        "🛑 `.ghoulstop` — Остановить цикл 1000-7.\n"
        "👤 `.info` — Информация о пользователе.\n"
        "🎭 `.a_troll` — Включить/выключить авто-троллинг.\n"
        "💤 `.afk [причина]` / `.unafk` — Быстрый автоответчик.\n"
        "📌 `.note [имя] [текст]` / `.get [имя]` — Заметки.\n"
        "✍️ `.fix [текст]` — Исправить и оформить текст.\n"
        "🛑 `.stop` — Остановить активный спам.\n"
        "🎮 `.starts` — Игра «Камень, ножницы, бумага»."
    )
    await callback_query.message.edit_text(free_text, reply_markup=get_back_to_help_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "show_paid_commands")
async def process_paid_commands_callback(callback_query: CallbackQuery):
    paid_text = (
        "⭐ **Платные Премиум-функции:**\n"
        f"_(Доступны после оплаты **{PREMIUM_PRICE_STARS} Stars**)_\n\n"
        "💸 `.send [сумма]` — Сгенерировать фейк чек Crypto Bot\n"
        "🚀 `.spam [текст]` — Спам с задержкой 1.5 сек\n"
        "⚡ `.killerspam [текст]` — Моментальный спам"
    )
    await callback_query.message.edit_text(paid_text, reply_markup=get_back_to_help_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "show_game_info")
async def process_game_info_callback(callback_query: CallbackQuery):
    await callback_query.message.answer("🎮 Запустите дуэль командой: `.starts`", parse_mode="Markdown")
    await callback_query.answer()

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
        if chat_id in active_games: 
            del active_games[chat_id]
        try: 
            await callback_query.message.delete()
        except: 
            await callback_query.message.edit_text("❌ Игра завершена.")

@dp.callback_query(lambda c: c.data and c.data.startswith("rps_"))
async def process_rps_choice(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    choice, chat_id = parts[1], int(parts[2])
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name

    if chat_id not in active_games:
        await callback_query.answer("Игра не найдена. Напишите .starts", show_alert=True)
        return

    game = active_games[chat_id]

    if user_id in game["choices"]:
        await callback_query.answer("Вы уже сделали свой выбор! Ожидайте второго игрока.", show_alert=True)
        return

    game["choices"][user_id] = {"choice": choice, "name": user_name}
    chosen_text = RPS_NAMES.get(choice, choice)
    await callback_query.answer(f"Вы выбрали: {chosen_text}!")

    count = len(game["choices"])

    if count == 1:
        text = (
            f"🎮 **Дуэль: Камень, ножницы, бумага!**\n\n"
            f"👤 **{user_name}** сделал свой выбор!\n"
            f"📊 Проголосовало: **1/2** игроков.\n\n"
            f"⏳ Второму игроку нужно сделать выбор ниже:"
        )
        await callback_query.message.edit_text(text, reply_markup=get_rps_keyboard(chat_id), parse_mode="Markdown")

    elif count >= 2:
        players = list(game["choices"].values())
        p1, p2 = players[0], players[1]

        status_msg = (
            f"🎮 **Дуэль: Камень, ножницы, бумага!**\n\n"
            f"📊 Проголосовало: **2/2** игроков!\n"
            f"✅ Оба игрока сделали выбор!\n\n"
        )

        for i in range(3, 0, -1):
            await callback_query.message.edit_text(
                f"{status_msg}⏳ Подведение итогов через **{i}** сек...",
                parse_mode="Markdown"
            )
            await asyncio.sleep(1)

        c1, c2 = p1["choice"], p2["choice"]

        if c1 == c2:
            result = "🤝 **Ничья!**"
        elif (c1 == "rock" and c2 == "scissors") or (c1 == "scissors" and c2 == "paper") or (c1 == "paper" and c2 == "rock"):
            result = f"🏆 Победил **{p1['name']}**!"
        else:
            result = f"🏆 Победил **{p2['name']}**!"

        res_text = (
            f"🎮 **Результаты дуэли:**\n\n"
            f"👤 **{p1['name']}** выбрал: {RPS_NAMES.get(c1)}\n"
            f"👤 **{p2['name']}** выбрал: {RPS_NAMES.get(c2)}\n\n"
            f"{result}"
        )
        await callback_query.message.edit_text(res_text, reply_markup=get_post_game_keyboard(chat_id), parse_mode="Markdown")

# --- ОСНОВНОЙ ОБРАБОТЧИК TELEGRAM BUSINESS ---

@dp.business_message()
async def handle_business_message(message: Message):
    global active_spams, active_trolls, active_ghouls, active_games, afk_status, notes
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = (message.text or "").strip()

    # ПРОВЕРКА: Если сообщение написано в рамках Business-подключения,
    # проверяем, от кого оно пришло. Если текст начинается с точки (команда),
    # но пишет СОБЕСЕДНИК, а не ВЛАДЕЛЕЦ аккаунта — игнорируем команды.
    # В Telegram Business исходящие сообщения владельца имеют message.from_user.id == id владельца.
    
    # 1. Автоответчик (AFK) работает, только если пишет СОБЕСЕДНИК (не хозяин)
    if afk_status["active"] and message.chat.type == "private":
        # Отвечаем автоответчиком только на входящие
        if message.from_user and message.from_user.id != message.chat.id:
            await bot.send_message(
                chat_id=chat_id,
                text=afk_status["reason"],
                business_connection_id=message.business_connection_id
            )
            return

    if text.startswith("."):
        # Если команду пытается выполнить чужой аккаунт (собеседник), не выполняем бизнес-команды
        # Важно: В Telegram Business отправленные ВАМИ сообщения обрабатываются бота от ВАШЕГО user_id.
        if text.startswith(".afk"):
            reason = text[4:].strip() or "Сплю"
            afk_status["active"] = True
            afk_status["reason"] = reason
            await bot.send_message(
                chat_id=chat_id,
                text=f"💤 **Режим AFK включен.**\nПричина: {reason}",
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text.startswith(".unafk"):
            afk_status["active"] = False
            await bot.send_message(
                chat_id=chat_id,
                text="☀️ **Режим AFK выключен.**",
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text == ".ghoulstop":
            active_ghouls[chat_id] = False
            await bot.send_message(
                chat_id=chat_id,
                text="🛑 **Цикл 1000-7 остановлен.**",
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text == ".cat":
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.thecatapi.com/v1/images/search") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=data[0]["url"],
                            caption="🐱 Вот твой случайный котик!",
                            business_connection_id=message.business_connection_id
                        )
            return

        elif text == ".ghoul":
            if active_ghouls.get(chat_id, False): return
            active_ghouls[chat_id] = True
            val = 1000
            while val > 0 and active_ghouls.get(chat_id, False):
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{val} - 7 = {val - 7}",
                    business_connection_id=message.business_connection_id
                )
                val -= 7
                await asyncio.sleep(0.3)
                if val < 7: break
            if active_ghouls.get(chat_id, False):
                await bot.send_message(
                    chat_id=chat_id,
                    text="я гуль...",
                    business_connection_id=message.business_connection_id
                )
            active_ghouls[chat_id] = False
            return

        elif text == ".info":
            user = message.from_user
            info_msg = (
                f"👤 **Информация о пользователе:**\n\n"
                f"• **Имя:** {user.first_name}\n"
                f"• **ID:** `{user.id}`\n"
                f"• **Username:** @{user.username if user.username else 'отсутствует'}\n"
                f"• **Премиум:** {'Да' if user.is_premium else 'Нет'}"
            )
            await bot.send_message(
                chat_id=chat_id,
                text=info_msg,
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text == ".a_troll":
            current_status = active_trolls.get(chat_id, False)
            active_trolls[chat_id] = not current_status
            status_text = "включен 🎭" if active_trolls[chat_id] else "выключен 🛑"
            await bot.send_message(
                chat_id=chat_id,
                text=f"Режим авто-троллинга **{status_text}**",
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        # ПЛАТНАЯ КОМАНДА: .send
        elif text.startswith(".send"):
            if user_id not in premium_users:
                await send_premium_invoice(user_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⭐ **Команда доступна только Премиум-пользователям!**\nСчет на оплату ({PREMIUM_PRICE_STARS} Stars) отправлен вам в ЛС с ботом.",
                    business_connection_id=message.business_connection_id
                )
                return

            amount = text[5:].strip() or "10"
            check_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"Получить {amount} USDT 💬", url="https://t.me/send")]
            ])
            await bot.send_message(
                chat_id=chat_id,
                text=f"✅ **Вы получили чек на {amount} USDT ($ {amount})**\n\nНажмите кнопку ниже, чтобы забрать средства.",
                reply_markup=check_markup,
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text.startswith(".note"):
            args = text[5:].strip().split(maxsplit=1)
            if len(args) == 2:
                notes[args[0].lower()] = args[1]
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"📌 Заметка **'{args[0]}'** сохранена!",
                    business_connection_id=message.business_connection_id,
                    parse_mode="Markdown"
                )
            return

        elif text.startswith(".get"):
            note_name = text[4:].strip().lower()
            res = notes.get(note_name, f"❌ Заметка **'{note_name}'** не найдена.")
            await bot.send_message(
                chat_id=chat_id,
                text=res,
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text.startswith(".fix"):
            raw = text[4:].strip()
            if raw:
                fixed = raw.capitalize() + ("." if not raw.endswith(('.', '!', '?')) else "")
                await bot.send_message(
                    chat_id=chat_id,
                    text=fixed,
                    business_connection_id=message.business_connection_id
                )
            return

        elif text == ".starts":
            active_games[chat_id] = {"choices": {}}
            await bot.send_message(
                chat_id=chat_id,
                text="🎮 **Дуэль: Камень, ножницы, бумага!**\n\n⏳ Ожидание игроков...\n📊 Проголосовало: **0/2**",
                reply_markup=get_rps_keyboard(chat_id),
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        # ПЛАТНАЯ КОМАНДА: .spam
        elif text.startswith(".spam"):
            if user_id not in premium_users:
                await send_premium_invoice(user_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⭐ **Команда доступна только Премиум-пользователям!**\nСчет на оплату ({PREMIUM_PRICE_STARS} Stars) отправлен вам в ЛС с ботом.",
                    business_connection_id=message.business_connection_id
                )
                return

            msg = text[5:].strip()
            if msg:
                active_spams[chat_id] = True
                while active_spams.get(chat_id, False):
                    await bot.send_message(chat_id=chat_id, text=msg, business_connection_id=message.business_connection_id)
                    await asyncio.sleep(1.5)
            return

        # ПЛАТНАЯ КОМАНДА: .killerspam
        elif text.startswith(".killerspam"):
            if user_id not in premium_users:
                await send_premium_invoice(user_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⭐ **Команда доступна только Премиум-пользователям!**\nСчет на оплату ({PREMIUM_PRICE_STARS} Stars) отправлен вам в ЛС с ботом.",
                    business_connection_id=message.business_connection_id
                )
                return

            msg = text[11:].strip()
            if msg:
                active_spams[chat_id] = True
                while active_spams.get(chat_id, False):
                    await bot.send_message(chat_id=chat_id, text=msg, business_connection_id=message.business_connection_id)
                    await asyncio.sleep(0.01)
            return

        elif text == ".stop":
            active_spams[chat_id] = False
            await bot.send_message(chat_id=chat_id, text="🛑 Спам остановлен.", business_connection_id=message.business_connection_id)
            return

    if active_trolls.get(chat_id, False):
        await bot.send_message(
            chat_id=chat_id,
            text=random.choice(TROLL_PHRASES),
            business_connection_id=message.business_connection_id
        )
        return

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
