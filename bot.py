import asyncio
import logging
import random
import os
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройки и токены
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    logging.warning("BOT_TOKEN не найден в переменных окружения. Укажите его перед запуском.")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

# Глобальные переменные управления
is_spamming = False
is_trolling = False
is_ghouling = False

# Состояние AFK (автоответчика)
afk_status = {"active": False, "reason": "Занят"}

# Состояния FSM для ввода текста автоответчика
class AFKState(StatesGroup):
    waiting_for_text = State()

# Локальное хранилище данных (вместо Supabase)
notes = {}
active_games = {}
users_db = {}

# Список фраз для авто-троллинга (.a_troll)
TROLL_PHRASES = [
    "Спорить с тобой — это как играть в шахматы с голубем.",
    "Ты всегда такой умный или сегодня особенный день?",
    "Ага, очень интересно, продолжай (нет).",
    "Мнение принято, отправлено в корзину.",
    "1000-7, гуль, получается?"
]

# Локальная регистрация пользователя
async def get_or_create_user(user_id: int, username: str):
    if user_id not in users_db:
        users_db[user_id] = {"id": user_id, "username": username, "balance": 100}
        return users_db[user_id], True
    return users_db[user_id], False

# Главная панель управления (Клавиатура)
def get_main_keyboard():
    afk_btn_text = "🔴 Отключить автоответчик" if afk_status["active"] else "💤 Включить автоответчик"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=afk_btn_text, callback_data="toggle_afk_panel")],
        [
            InlineKeyboardButton(text="📖 Инструкция", callback_data="show_help"),
            InlineKeyboardButton(text="🎮 Игра", callback_data="show_game_info")
        ]
    ])

# Клавиатура подменю Инструкции (Бесплатные / Платные)
def get_help_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🆓 Бесплатные команды", callback_data="show_free_commands"),
            InlineKeyboardButton(text="⭐ Платные функции", callback_data="show_paid_commands")
        ]
    ])

# Клавиатура возврата в меню Инструкции
def get_back_to_help_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню инструкций", callback_data="show_help")]
    ])

# Клавиатура подтверждения отключения
def get_confirm_turnoff_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отключить", callback_data="confirm_afk_off"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="cancel_afk_off")
        ]
    ])

# Игра КНБ
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

# Нажатие на кнопку Автоответчика в панели
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

# Прием текста автоответчика от пользователя
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

# Подтверждение отключения (Кнопка Да)
@dp.callback_query(F.data == "confirm_afk_off")
async def process_confirm_afk_off(callback_query: CallbackQuery):
    afk_status["active"] = False
    await callback_query.message.edit_text("☀️ **Автоответчик выключен.**", parse_mode="Markdown")
    await callback_query.answer("Автоответчик выключен!")

# Отмена отключения (Кнопка Нет)
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
        "🎮 `.starts` — Игра «Камень, ножницы, бумага»."
    )
    await callback_query.message.edit_text(free_text, reply_markup=get_back_to_help_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "show_paid_commands")
async def process_paid_commands_callback(callback_query: CallbackQuery):
    paid_text = (
        "⭐ **Платные / Премиум функции:**\n\n"
        "💸 `.send [сумма]` — Сгенерировать фейк чек Crypto Bot.\n"
        "🚀 `.spam [текст]` — Обычный спам сообщениями.\n"
        "⚡ `.killerspam [текст]` — Скоростной спам (0.1 сек).\n"
        "🛑 `.stop` — Остановить активный спам."
    )
    await callback_query.message.edit_text(paid_text, reply_markup=get_back_to_help_keyboard(), parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "show_game_info")
async def process_game_info_callback(callback_query: CallbackQuery):
    await callback_query.message.answer("🎮 Запустите дуэль командой: `.starts`", parse_mode="Markdown")
    await callback_query.answer()

# Игра КНБ Handlers
@dp.callback_query(lambda c: c.data and (c.data.startswith("rps_restart_") or c.data.startswith("rps_cancel_")))
async def process_post_game_actions(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    action, chat_id = parts[1], int(parts[2])

    if action == "restart":
        active_games[chat_id] = {"choices": {}}
        await callback_query.message.edit_text("🎮 **Дуэль: Камень, ножницы, бумага!**", reply_markup=get_rps_keyboard(chat_id))
    elif action == "cancel":
        if chat_id in active_games: del active_games[chat_id]
        try: await callback_query.message.delete()
        except: await callback_query.message.edit_text("❌ Игра завершена.")

@dp.callback_query(lambda c: c.data and c.data.startswith("rps_"))
async def process_rps_choice(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")
    choice, chat_id = parts[1], int(parts[2])
    user_id, user_name = callback_query.from_user.id, callback_query.from_user.first_name

    if chat_id not in active_games:
        await callback_query.answer("Игра не найдена. Напишите .starts", show_alert=True)
        return

    game = active_games[chat_id]
    game["choices"][user_id] = {"choice": choice, "name": user_name}
    await callback_query.answer(f"Вы выбрали {choice.upper()}!")

    if len(game["choices"]) >= 2:
        await callback_query.message.edit_text("⏳ Подсчитываем результаты...")
        await asyncio.sleep(2)
        players = list(game["choices"].values())
        p1, p2 = players[0], players[1]
        c1, c2 = p1["choice"], p2["choice"]

        if c1 == c2: result = "🤝 **Ничья!**"
        elif (c1=="rock" and c2=="scissors") or (c1=="scissors" and c2=="paper") or (c1=="paper" and c2=="rock"):
            result = f"🏆 Победил **{p1['name']}**!"
        else:
            result = f"🏆 Победил **{p2['name']}**!"

        res_text = f"🎮 **Результаты:**\n👤 **{p1['name']}**: {c1}\n👤 **{p2['name']}**: {c2}\n\n{result}"
        await callback_query.message.edit_text(res_text, reply_markup=get_post_game_keyboard(chat_id), parse_mode="Markdown")

# --- ОСНОВНОЙ ОБРАБОТЧИК TELEGRAM BUSINESS ---

@dp.business_message()
async def handle_business_message(message: Message):
    global is_spamming, is_trolling, is_ghouling, active_games, afk_status, notes
    
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # 1. ОБРАБОТКА ВАШИХ КОМАНД (Начинаются с точки ".")
    if text.startswith("."):
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
            is_ghouling = False
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
            if is_ghouling: return
            is_ghouling = True
            val = 1000
            while val > 0 and is_ghouling:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{val} - 7 = {val - 7}",
                    business_connection_id=message.business_connection_id
                )
                val -= 7
                await asyncio.sleep(0.3)
                if val < 7: break
            if is_ghouling:
                await bot.send_message(
                    chat_id=chat_id,
                    text="я гуль...",
                    business_connection_id=message.business_connection_id
                )
            is_ghouling = False
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
            is_trolling = not is_trolling
            status = "включен 🎭" if is_trolling else "выключен 🛑"
            await bot.send_message(
                chat_id=chat_id,
                text=f"Режим авто-троллинга **{status}**",
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text.startswith(".send"):
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
                text="🎮 **Дуэль: Камень, ножницы, бумага!**",
                reply_markup=get_rps_keyboard(chat_id),
                business_connection_id=message.business_connection_id,
                parse_mode="Markdown"
            )
            return

        elif text.startswith(".spam"):
            msg = text[5:].strip()
            if msg:
                is_spamming = True
                while is_spamming:
                    await bot.send_message(chat_id=chat_id, text=msg, business_connection_id=message.business_connection_id)
                    await asyncio.sleep(1.5)
            return

        elif text.startswith(".killerspam"):
            msg = text[11:].strip()
            if msg:
                is_spamming = True
                while is_spamming:
                    await bot.send_message(chat_id=chat_id, text=msg, business_connection_id=message.business_connection_id)
                    await asyncio.sleep(0.1)
            return

        elif text == ".stop":
            is_spamming = False
            await bot.send_message(chat_id=chat_id, text="🛑 Спам остановлен.", business_connection_id=message.business_connection_id)
            return

    # 2. ОБРАБОТКА ВХОДЯЩИХ СООБЩЕНИЙ ОТ СОБЕСЕДНИКОВ (Только Личные Чаты)
    if afk_status["active"] and message.chat.type == "private":
        await bot.send_message(
            chat_id=chat_id,
            text=afk_status["reason"],
            business_connection_id=message.business_connection_id
        )
        return

    if is_trolling:
        await bot.send_message(
            chat_id=chat_id,
            text=random.choice(TROLL_PHRASES),
            business_connection_id=message.business_connection_id
        )
        return

async def main():
    logging.basicConfig(level=logging.INFO)
    if not bot:
        logging.error("Невозможно запустить бота: BOT_TOKEN не задан.")
        return
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
