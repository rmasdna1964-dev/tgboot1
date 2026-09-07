import asyncio
import logging
import random
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client, Client

# Настройки и ключи
BOT_TOKEN = "8872260684:AAHEhMfCuLTfG0RK1kjmqUmDS-TXRiQUWzk"[cite: 1]
SUPABASE_URL = "https://uzdorwhlwihwhvnedwkj.supabase.co"[cite: 1]
SUPABASE_KEY = "sb_publishable_GvTORvdPKyFzSp3Kjlx2HA_9OBY9xx-"[cite: 1]

# Инициализация Supabase, бота и диспетчера
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)[cite: 1]
bot = Bot(token=BOT_TOKEN)[cite: 1]
dp = Dispatcher(storage=MemoryStorage())[cite: 1]

# Глобальные переменные управления (по чатам)
active_trolls = {}   # chat_id: bool
is_ghouling = False[cite: 1]

# Состояние AFK (автоответчика)
afk_status = {"active": False, "reason": "Занят"}[cite: 1]

# Состояния FSM для ввода текста автоответчика
class AFKState(StatesGroup):
    waiting_for_text = State()[cite: 1]

# Хранилище заметок и активных игр
notes = {}[cite: 1]
active_games = {}[cite: 1]

# Список фраз для авто-троллинга (.a_troll)
TROLL_PHRASES = [
    "Спорить с тобой — это как играть в шахматы с голубем.",[cite: 1]
    "Ты всегда такой умный или сегодня особенный день?",[cite: 1]
    "Ага, очень интересно, продолжай (нет).",[cite: 1]
    "Мнение принято, отправлено в корзину.",[cite: 1]
    "1000-7, гуль, получается?"[cite: 1]
]

# Регистрация / получение пользователя в Supabase
async def get_or_create_user(user_id: int, username: str):
    try:
        response = supabase.table("profiles").select("*").eq("id", user_id).execute()[cite: 1]
        if not response.data:[cite: 1]
            new_user = {"id": user_id, "username": username, "balance": 100}[cite: 1]
            data = supabase.table("profiles").insert(new_user).execute()[cite: 1]
            return data.data[0], True[cite: 1]
        return response.data[0], False[cite: 1]
    except Exception as e:
        logging.error(f"Ошибка БД: {e}")[cite: 1]
        return None, False[cite: 1]

# Главная панель управления (Клавиатура)
def get_main_keyboard():
    afk_btn_text = "🔴 Отключить автоответчик" if afk_status["active"] else "💤 Включить автоответчик"[cite: 1]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=afk_btn_text, callback_data="toggle_afk_panel")],[cite: 1]
        [
            InlineKeyboardButton(text="📖 Инструкция", callback_data="show_help"),[cite: 1]
            InlineKeyboardButton(text="🎮 Игра", callback_data="show_game_info")[cite: 1]
        ]
    ])

# Клавиатура подтверждения отключения
def get_confirm_turnoff_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отключить", callback_data="confirm_afk_off"),[cite: 1]
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="cancel_afk_off")[cite: 1]
        ]
    ])

# Игра КНБ
def get_rps_keyboard(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗿 Камень", callback_data=f"rps_rock_{chat_id}"),[cite: 1]
            InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"rps_scissors_{chat_id}"),[cite: 1]
            InlineKeyboardButton(text="📄 Бумага", callback_data=f"rps_paper_{chat_id}")[cite: 1]
        ]
    ])

def get_post_game_keyboard(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 Сыграть ещё раз", callback_data=f"rps_restart_{chat_id}"),[cite: 1]
            InlineKeyboardButton(text="❌ Не хочу играть", callback_data=f"rps_cancel_{chat_id}")[cite: 1]
        ]
    ])

# --- КОМАНДА /start И ПАНЕЛЬ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()[cite: 1]
    user_id = message.from_user.id[cite: 1]
    username = message.from_user.username or "Аноним"[cite: 1]
    await get_or_create_user(user_id, username)[cite: 1]
    
    status_text = f"Статус автоответчика: **{'ВКЛЮЧЕН 🟢' if afk_status['active'] else 'ВЫКЛЮЧЕН 🔴'}**"[cite: 1]
    if afk_status["active"]:[cite: 1]
        status_text += f"\nТекущий текст: _{afk_status['reason']}_"[cite: 1]

    text = f"Привет, {username}!\nПанель управления Telegram Business.\n\n{status_text}"[cite: 1]
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")[cite: 1]

# Нажатие на кнопку Автоответчика в панели
@dp.callback_query(F.data == "toggle_afk_panel")
async def process_afk_toggle_click(callback_query: CallbackQuery, state: FSMContext):
    if not afk_status["active"]:[cite: 1]
        await state.set_state(AFKState.waiting_for_text)[cite: 1]
        await callback_query.message.answer("⌨️ **Напишите текст для автоответчика:**\n_(Этот текст будет отправляться всем в ЛС)_", parse_mode="Markdown")[cite: 1]
        await callback_query.answer()[cite: 1]
    else:
        await callback_query.message.answer([cite: 1]
            "⚠️ **Точно отключить автоответчик?**",[cite: 1]
            reply_markup=get_confirm_turnoff_keyboard(),[cite: 1]
            parse_mode="Markdown"[cite: 1]
        )
        await callback_query.answer()[cite: 1]

# Прием текста автоответчика от пользователя
@dp.message(AFKState.waiting_for_text)
async def process_afk_text_input(message: Message, state: FSMContext):
    text = message.text.strip()[cite: 1]
    afk_status["active"] = True[cite: 1]
    afk_status["reason"] = text[cite: 1]
    await state.clear()[cite: 1]
    
    await message.answer([cite: 1]
        f"✅ **Автоответчик успешно включен!**\n\nТекст ответа:\n_{text}_",[cite: 1]
        reply_markup=get_main_keyboard(),[cite: 1]
        parse_mode="Markdown"[cite: 1]
    )

# Подтверждение отключения (Кнопка Да)
@dp.callback_query(F.data == "confirm_afk_off")
async def process_confirm_afk_off(callback_query: CallbackQuery):
    afk_status["active"] = False[cite: 1]
    await callback_query.message.edit_text("☀️ **Автоответчик выключен.**", parse_mode="Markdown")[cite: 1]
    await callback_query.answer("Автоответчик выключен!")[cite: 1]

# Отмена отключения (Кнопка Нет)
@dp.callback_query(F.data == "cancel_afk_off")
async def process_cancel_afk_off(callback_query: CallbackQuery):
    await callback_query.message.edit_text("👍 Автоответчик остался **включенным**.", parse_mode="Markdown")[cite: 1]
    await callback_query.answer()[cite: 1]

# --- CALLBACKS ИНСТРУКЦИИ И ИГРЫ ---

@dp.callback_query(F.data == "show_help")
async def process_help_callback(callback_query: CallbackQuery):
    help_text = ([cite: 1]
        "**Все доступные команды (FREE):**\n\n"[cite: 1]
        "🐱 `.cat` — Случайное фото котика.\n"[cite: 1]
        "⚡ `.ghoul` — Цикл 1000-7 (Dead Inside).\n"[cite: 1]
        "🛑 `.ghoulstop` — Остановить цикл 1000-7.\n"[cite: 1]
        "👤 `.info` — Информация о пользователе.\n"[cite: 1]
        "🎭 `.a_troll` — Включить/выключить авто-троллинг.\n"[cite: 1]
        "💸 `.send [сумма]` — Сгенерировать фейк чек Crypto Bot.\n"[cite: 1]
        "💤 `.afk [причина]` / `.unafk` — Быстрый автоответчик.\n"[cite: 1]
        "📌 `.note [имя] [текст]` / `.get [имя]` — Быстрые шаблоны.\n"[cite: 1]
        "✍️ `.fix [текст]` — Исправить и оформить текст.\n"[cite: 1]
        "🎮 `.starts` — Игра «Камень, ножницы, бумага»."
    )
    await callback_query.message.answer(help_text, parse_mode="Markdown")[cite: 1]
    await callback_query.answer()[cite: 1]

@dp.callback_query(F.data == "show_game_info")
async def process_game_info_callback(callback_query: CallbackQuery):
    await callback_query.message.answer("🎮 Запустите дуэль командой: `.starts`", parse_mode="Markdown")[cite: 1]
    await callback_query.answer()[cite: 1]

# Игра КНБ Handlers
@dp.callback_query(lambda c: c.data and (c.data.startswith("rps_restart_") or c.data.startswith("rps_cancel_")))
async def process_post_game_actions(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")[cite: 1]
    action, chat_id = parts[1], int(parts[2])[cite: 1]

    if action == "restart":[cite: 1]
        active_games[chat_id] = {"choices": {}}[cite: 1]
        await callback_query.message.edit_text("🎮 **Дуэль: Камень, ножницы, бумага!**", reply_markup=get_rps_keyboard(chat_id))[cite: 1]
    elif action == "cancel":[cite: 1]
        if chat_id in active_games: del active_games[chat_id][cite: 1]
        try: await callback_query.message.delete()[cite: 1]
        except: await callback_query.message.edit_text("❌ Игра завершена.")[cite: 1]

@dp.callback_query(lambda c: c.data and c.data.startswith("rps_"))
async def process_rps_choice(callback_query: CallbackQuery):
    parts = callback_query.data.split("_")[cite: 1]
    choice, chat_id = parts[1], int(parts[2])[cite: 1]
    user_id, user_name = callback_query.from_user.id, callback_query.from_user.first_name[cite: 1]

    if chat_id not in active_games:[cite: 1]
        await callback_query.answer("Игра не найдена. Напишите .starts", show_alert=True)[cite: 1]
        return

    game = active_games[chat_id][cite: 1]
    game["choices"][user_id] = {"choice": choice, "name": user_name}[cite: 1]
    await callback_query.answer(f"Вы выбрали {choice.upper()}!")[cite: 1]

    if len(game["choices"]) >= 2:[cite: 1]
        await callback_query.message.edit_text("⏳ Подсчитываем результаты...")[cite: 1]
        await asyncio.sleep(2)[cite: 1]
        players = list(game["choices"].values())[cite: 1]
        p1, p2 = players[0], players[1][cite: 1]
        c1, c2 = p1["choice"], p2["choice"][cite: 1]

        if c1 == c2: result = "🤝 **Ничья!**"[cite: 1]
        elif (c1=="rock" and c2=="scissors") or (c1=="scissors" and c2=="paper") or (c1=="paper" and c2=="rock"):[cite: 1]
            result = f"🏆 Победил **{p1['name']}**!"[cite: 1]
        else:
            result = f"🏆 Победил **{p2['name']}**!"[cite: 1]

        res_text = f"🎮 **Результаты:**\n👤 **{p1['name']}**: {c1}\n👤 **{p2['name']}**: {c2}\n\n{result}"[cite: 1]
        await callback_query.message.edit_text(res_text, reply_markup=get_post_game_keyboard(chat_id), parse_mode="Markdown")[cite: 1]

# --- ОСНОВНОЙ ОБРАБОТЧИК TELEGRAM BUSINESS ---

@dp.business_message()
async def handle_business_message(message: Message):
    global active_trolls, is_ghouling, active_games, afk_status, notes
    
    chat_id = message.chat.id[cite: 1]
    user_id = message.from_user.id
    text = (message.text or "").strip()[cite: 1]
    conn_id = message.business_connection_id

    if not conn_id:
        return

    # Проверка автора сообщения
    is_me = (user_id != chat_id)         # Написали вы (владелец бизнес-аккаунта)
    is_partner = (user_id == chat_id)    # Написал ваш собеседник

    # =============================================================
    # 1. КОМАНДЫ, КОТОРЫЕ ВВОДИТЕ ВЫ (ВЛАДЕЛЕЦ)
    # =============================================================
    if is_me:
        if text.startswith("."):
            if text.startswith(".afk"):
                reason = text[4:].strip() or "Сплю"[cite: 1]
                afk_status["active"] = True[cite: 1]
                afk_status["reason"] = reason[cite: 1]
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"💤 **Режим AFK включен.**\nПричина: {reason}",[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text.startswith(".unafk"):
                afk_status["active"] = False[cite: 1]
                await bot.send_message(
                    chat_id=chat_id,
                    text="☀️ **Режим AFK выключен.**",[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text == ".ghoulstop":
                is_ghouling = False[cite: 1]
                await bot.send_message(
                    chat_id=chat_id,
                    text="🛑 **Цикл 1000-7 остановлен.**",[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text == ".cat":
                async with aiohttp.ClientSession() as session:[cite: 1]
                    async with session.get("https://api.thecatapi.com/v1/images/search") as resp:[cite: 1]
                        if resp.status == 200:[cite: 1]
                            data = await resp.json()[cite: 1]
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=data[0]["url"],[cite: 1]
                                caption="🐱 Вот твой случайный котик!",[cite: 1]
                                business_connection_id=conn_id
                            )
                return

            elif text == ".ghoul":
                if is_ghouling: return[cite: 1]
                is_ghouling = True[cite: 1]
                val = 1000[cite: 1]
                while val > 0 and is_ghouling:[cite: 1]
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"{val} - 7 = {val - 7}",[cite: 1]
                        business_connection_id=conn_id
                    )
                    val -= 7[cite: 1]
                    await asyncio.sleep(0.3)[cite: 1]
                    if val < 7: break[cite: 1]
                if is_ghouling:[cite: 1]
                    await bot.send_message(
                        chat_id=chat_id,
                        text="я гуль...",[cite: 1]
                        business_connection_id=conn_id
                    )
                is_ghouling = False[cite: 1]
                return

            elif text == ".info":
                user = message.from_user[cite: 1]
                info_msg = (
                    f"👤 **Информация о пользователе:**\n\n"[cite: 1]
                    f"• **Имя:** {user.first_name}\n"[cite: 1]
                    f"• **ID:** `{user.id}`\n"[cite: 1]
                    f"• **Username:** @{user.username if user.username else 'отсутствует'}\n"[cite: 1]
                    f"• **Премиум:** {'Да' if user.is_premium else 'Нет'}"[cite: 1]
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=info_msg,[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text == ".a_troll":
                current_status = active_trolls.get(chat_id, False)
                active_trolls[chat_id] = not current_status
                status = "включен 🎭" if active_trolls[chat_id] else "выключен 🛑"
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Режим авто-троллинга **{status}**",[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text.startswith(".send"):
                amount = text[5:].strip() or "10"[cite: 1]
                check_markup = InlineKeyboardMarkup(inline_keyboard=[[cite: 1]
                    [InlineKeyboardButton(text=f"Получить {amount} USDT 💬", url="https://t.me/send")][cite: 1]
                ])
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ **Вы получили чек на {amount} USDT ($ {amount})**\n\nНажмите кнопку ниже, чтобы забрать средства.",[cite: 1]
                    reply_markup=check_markup,[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text.startswith(".note"):
                args = text[5:].strip().split(maxsplit=1)[cite: 1]
                if len(args) == 2:[cite: 1]
                    notes[args[0].lower()] = args[1][cite: 1]
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"📌 Заметка **'{args[0]}'** сохранена!",[cite: 1]
                        business_connection_id=conn_id,
                        parse_mode="Markdown"
                    )
                return

            elif text.startswith(".get"):
                note_name = text[4:].strip().lower()[cite: 1]
                res = notes.get(note_name, f"❌ Заметка **'{note_name}'** не найдена.")[cite: 1]
                await bot.send_message(
                    chat_id=chat_id,
                    text=res,[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

            elif text.startswith(".fix"):
                raw = text[4:].strip()[cite: 1]
                if raw:[cite: 1]
                    fixed = raw.capitalize() + ("." if not raw.endswith(('.', '!', '?')) else "")[cite: 1]
                    await bot.send_message(
                        chat_id=chat_id,
                        text=fixed,[cite: 1]
                        business_connection_id=conn_id
                    )
                return

            elif text == ".starts":
                active_games[chat_id] = {"choices": {}}[cite: 1]
                await bot.send_message(
                    chat_id=chat_id,
                    text="🎮 **Дуэль: Камень, ножницы, бумага!**",[cite: 1]
                    reply_markup=get_rps_keyboard(chat_id),[cite: 1]
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

    # =============================================================
    # 2. ОБРАБОТКА ВХОДЯЩИХ СООБЩЕНИЙ ОТ СОБЕСЕДНИКА
    # =============================================================
    if is_partner:
        # Автоответчик AFK
        if afk_status["active"] and message.chat.type == "private":[cite: 1]
            await bot.send_message(
                chat_id=chat_id,
                text=afk_status["reason"],[cite: 1]
                business_connection_id=conn_id
            )
            return

        # Авто-троллинг
        if active_trolls.get(chat_id, False):
            await bot.send_message(
                chat_id=chat_id,
                text=random.choice(TROLL_PHRASES),[cite: 1]
                business_connection_id=conn_id
            )
            return

        # Команды собеседника
        if text.startswith("."):
            if text == ".info":
                user = message.from_user
                info_msg = (
                    f"👤 **Информация о собеседнике:**\n\n"
                    f"• **Имя:** {user.first_name}\n"
                    f"• **ID:** `{user.id}`\n"
                    f"• **Username:** @{user.username if user.username else 'отсутствует'}"
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
                    text="🎮 **Дуэль: Камень, ножницы, бумага!**",
                    reply_markup=get_rps_keyboard(chat_id),
                    business_connection_id=conn_id,
                    parse_mode="Markdown"
                )
                return

async def main():
    logging.basicConfig(level=logging.INFO)[cite: 1]
    await dp.start_polling(bot)[cite: 1]

if __name__ == "__main__":
    asyncio.run(main())[cite: 1]
