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
🛡️ <b>SafeSaverX</b>

Привет! Я сохраняю удалённые и отредактированные сообщения, чтобы ты ничего не терял.

▸ Статус: <b>{'активен' if user.is_active else 'неактивен'}</b>
▸ SAVE MODE: <b>{'включен' if user.savemode_enabled else 'выключен'}</b>
▸ Business: <b>{'подключен' if has_business else 'не подключен'}</b>
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
                url="tg://settings"
            )
        ],
        [
            InlineKeyboardButton(text="📖 Команды", callback_data="show_help"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
        ]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


# ✅ КОПИРОВАНИЕ USERNAME
@router.callback_query(lambda c: c.data == "copy_username")
async def copy_username(callback):
    await callback.answer(
        text="✅ @SafeSaverX_bot скопирован!\n\n"
             "Перейди в Настройки → Редактирование профиля → "
             "Автоматизация действий и вставь username.",
        show_alert=True
    )


# ✅ ПОМОЩЬ / ОПИСАНИЕ КОМАНД
@router.message(Command("help"))
async def help_command(message: Message):
    help_text = """
<b>📚 Команды SafeSaverX</b>

/start — 🚀 Приветствие
/help — 📖 Список команд
/settings — ⚙️ Настройки
/savemode — 📝 SAVE MODE
/deleted — 🗑 Удалённые
/search — 🔍 Поиск
/edits — ✏️ Правки
/media — 🖼️ Медиа
/summary — 📋 Выжимка
/todos — ✅ Задачи
/remind — ⏰ Напоминание
/digest — 📰 Дайджест
/autoreply — 🤖 Автоответ
/profile — 👤 Профиль
/business_status — 📊 Статус
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
<b>⚙️ Настройки</b>

▸ SAVE MODE — сохранение сообщений
▸ Автоответчик — автоматические ответы
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 SAVE MODE", callback_data="savemode_settings"),
            InlineKeyboardButton(text="🤖 Автоответ", callback_data="autoreply_settings")
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
<b>📝 SAVE MODE</b>

▸ Включить / Выключить сохранение
▸ Просмотр удалённых сообщений
▸ Поиск по базе
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
<b>🤖 Автоответчик</b>

▸ Автоматические ответы на сообщения
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Включить", callback_data="autoreply_on"),
            InlineKeyboardButton(text="🤖 Выключить", callback_data="autoreply_off")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ ЗАГЛУШКИ ДЛЯ КНОПОК
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