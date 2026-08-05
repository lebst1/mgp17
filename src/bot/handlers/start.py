from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.business_repository import BusinessRepository

router = Router()


@router.message(Command("start"))
async def start_command(message: Message):
    user = await UserRepository.get_by_id(message.from_user.id)
    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    has_business = len(connections) > 0
    
    welcome_text = f"""
🛡️ <b>Добро пожаловать в SafeSaverX!</b>

Я — твой надёжный хранитель сообщений в Telegram. 
Сохраняю удалённые и отредактированные сообщения, чтобы ты ничего не терял.

━━━━━━━━━━━━━━━━━━━━━━
<b>🔗 КАК ПОДКЛЮЧИТЬ БОТА</b>

1️⃣ Нажми на кнопку <b>«Скопировать @username»</b> ниже
2️⃣ Открой <b>Настройки</b> → <b>Редактирование профиля</b>
3️⃣ Выбери <b>«Автоматизация действий»</b>
4️⃣ Вставь скопированный @username бота
5️⃣ <b>ВАЖНО!</b> Дай <b>ВСЕ</b> разрешения на работу с сообщениями

━━━━━━━━━━━━━━━━━━━━━━
<b>✅ ЧТО УМЕЕТ БОТ</b>

📩 <b>Уведомления об удалении</b>
→ Когда собеседник удаляет сообщение

✏️ <b>Уведомления о правках</b>
→ Когда собеседник редактирует сообщение

📸 <b>Сохранение медиа</b>
→ Сгорающие фото, голосовые, видео

📊 <b>Твой статус:</b>
🔹 Аккаунт: <b>активен</b>
🔹 SAVE MODE: <b>{'включен ✅' if user.savemode_enabled else 'выключен ❌'}</b>
🔹 Business: <b>{'подключен ✅' if has_business else 'не подключен ❌'}</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📋 Скопировать @username",
                callback_data="copy_username"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Редактирование профиля",
                url="tg://settings"  # ✅ Открывает настройки Telegram
            )
        ],
        [
            InlineKeyboardButton(text="📖 Описание команд", callback_data="show_help"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
        ]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


# ✅ КОПИРОВАНИЕ USERNAME
@router.callback_query(lambda c: c.data == "copy_username")
async def copy_username(callback):
    await callback.answer(
        text="✅ @SafeSaverX_bot скопирован!\n\n"
             "Теперь перейди в Настройки → Редактирование профиля → "
             "Автоматизация действий и вставь туда этот username.",
        show_alert=True
    )


# ✅ ПОМОЩЬ / ОПИСАНИЕ КОМАНД
@router.message(Command("help"))
async def help_command(message: Message):
    help_text = """
📚 <b>Все команды SafeSaverX</b>

<i>Основные команды:</i>
/start — 🚀 Приветствие
/help — 📖 Список команд
/settings — ⚙️ Настройки

<i>📝 SAVE MODE:</i>
/savemode on — ✅ Включить сохранение
/savemode off — ❌ Выключить сохранение
/deleted — 🗑 Последние удалённые
/search текст — 🔍 Поиск по базе
/edits — ✏️ История правок
/media — 🖼️ Сохранённые медиа

<i>🤖 AI Функции:</i>
/summary чат — 📋 Выжимка последних сообщений
/todos — ✅ Список задач
/remind текст — ⏰ Создать напоминание
/digest now — 📰 Дайджест чатов
/autoreply on/off — 🤖 Автоответчик

<i>⚡ Dot команды:</i>
<code>.mute</code> — 🔇 Заглушить чат
<code>.unmute</code> — 🔊 Включить чат
<code>.info</code> — ℹ️ Информация о пользователе
<code>.repeat n текст</code> — 🔁 Повторить n раз
<code>.love</code> — ❤️ Анимация

<i>👤 Профиль:</i>
/profile — 👤 Мой профиль
/settings — ⚙️ Настройки
/business_status — 📊 Статус бизнеса
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Скопировать @username", callback_data="copy_username"),
            InlineKeyboardButton(text="✏️ Редактирование профиля", url="tg://settings")
        ],
        [
            InlineKeyboardButton(text="📊 Статус", callback_data="business_status"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ]
    ])
    
    await message.answer(help_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "show_help")
async def show_help(callback):
    await callback.answer()
    await help_command(callback.message)


# ✅ СТАТУС БИЗНЕСА
@router.callback_query(lambda c: c.data == "business_status")
async def show_business_status(callback):
    await callback.answer()
    from src.business_bot.handlers import business_status
    await business_status(callback.message)


# ✅ НАСТРОЙКИ
@router.callback_query(lambda c: c.data == "settings")
async def show_settings(callback):
    await callback.answer()
    settings_text = """
⚙️ <b>Настройки SafeSaverX</b>

🔹 <b>SAVE MODE</b> — сохранение удалённых сообщений
🔹 <b>AI Assistant</b> — умные функции
🔹 <b>Dot команды</b> — управление чатами

<i>Используй команды для настройки:</i>
/savemode on — ✅ включить SAVE MODE
/savemode off — ❌ выключить SAVE MODE
/autoreply on — 🤖 включить автоответ
/autoreply off — 🤖 выключить автоответ
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 SAVE MODE", callback_data="savemode_settings"),
            InlineKeyboardButton(text="🤖 Автоответчик", callback_data="autoreply_settings")
        ],
        [
            InlineKeyboardButton(text="📋 Скопировать @username", callback_data="copy_username"),
            InlineKeyboardButton(text="✏️ Редактирование профиля", url="tg://settings")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="show_help")
        ]
    ])
    
    await callback.message.edit_text(settings_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback):
    await callback.answer()
    await start_command(callback.message)


@router.callback_query(lambda c: c.data == "help")
async def help_callback(callback):
    await callback.answer()
    await help_command(callback.message)


@router.callback_query(lambda c: c.data == "savemode_settings")
async def savemode_settings(callback):
    await callback.answer()
    text = """
📝 <b>SAVE MODE</b>

Сохраняю удалённые и отредактированные сообщения.

<b>Команды:</b>
/savemode on — ✅ включить
/savemode off — ❌ выключить
/deleted — 🗑 последние удалённые
/search текст — 🔍 поиск
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Включить", callback_data="savemode_on"),
            InlineKeyboardButton(text="❌ Выключить", callback_data="savemode_off")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "autoreply_settings")
async def autoreply_settings(callback):
    await callback.answer()
    text = """
🤖 <b>Автоответчик</b>

Автоматически отвечаю на сообщения.

<b>Команды:</b>
/autoreply on — 🤖 включить
/autoreply off — 🤖 выключить
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Включить", callback_data="autoreply_on"),
            InlineKeyboardButton(text="🤖 Выключить", callback_data="autoreply_off")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ ЗАГЛУШКИ ДЛЯ КНОПОК (пока просто уведомления)
@router.callback_query(lambda c: c.data == "savemode_on")
async def savemode_on(callback):
    await callback.answer("✅ SAVE MODE включен! Используй /savemode on")


@router.callback_query(lambda c: c.data == "savemode_off")
async def savemode_off(callback):
    await callback.answer("❌ SAVE MODE выключен! Используй /savemode off")


@router.callback_query(lambda c: c.data == "autoreply_on")
async def autoreply_on(callback):
    await callback.answer("🤖 Автоответчик включен! Используй /autoreply on")


@router.callback_query(lambda c: c.data == "autoreply_off")
async def autoreply_off(callback):
    await callback.answer("🤖 Автоответчик выключен! Используй /autoreply off")