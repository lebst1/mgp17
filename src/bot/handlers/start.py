from aiogram import Router, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.business_repository import BusinessRepository

router = Router()


# ✅ ГЛАВНОЕ МЕНЮ (СТАРТ) — С ПРОВЕРКОЙ ПОЛЬЗОВАТЕЛЯ
@router.message(Command("start"))
async def start_command(message: Message):
    # ✅ ПРОВЕРЯЕМ, ЕСТЬ ЛИ ПОЛЬЗОВАТЕЛЬ В БД
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        # Если нет — создаём
        user = await UserRepository.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
    
    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    has_business = len(connections) > 0
    
    text = f"""
🛡️ <b>SafeSaverX</b>

Привет! Я сохраняю удалённые и отредактированные сообщения.

▸ Статус: <b>{'активен' if user.is_active else 'неактивен'}</b>
▸ SAVE MODE: <b>{'включен' if user.savemode_enabled else 'выключен'}</b>
▸ Business: <b>{'подключен' if has_business else 'не подключен'}</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Скопировать @username", callback_data="copy_username"),
            InlineKeyboardButton(text="✏️ Редактирование профиля", url="tg://settings")
        ],
        [
            InlineKeyboardButton(text="📖 Команды", callback_data="show_help"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
        ]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ КОПИРОВАНИЕ USERNAME
@router.callback_query(lambda c: c.data == "copy_username")
async def copy_username(callback: CallbackQuery):
    await callback.answer(
        text="✅ @SafeSaverX_bot скопирован!\n\nПерейди в Настройки → Редактирование профиля → Автоматизация действий и вставь username.",
        show_alert=True
    )


# ✅ ПОМОЩЬ / КОМАНДЫ
@router.callback_query(lambda c: c.data == "show_help")
async def show_help(callback: CallbackQuery):
    text = """
<b>📚 Команды SafeSaverX</b>

/start — 🚀 Приветствие
/help — 📖 Список команд
/settings — ⚙️ Настройки
/savemode — 📝 SAVE MODE
/deleted — 🗑 Удалённые
/search — 🔍 Поиск
/edits — ✏️ Правки
/media — 🖼️ Медиа
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
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ СТАТУС БИЗНЕСА
@router.callback_query(lambda c: c.data == "business_status")
async def show_business_status(callback: CallbackQuery):
    await callback.answer()
    from src.business_bot.handlers import business_status
    await business_status(callback.message)


# ✅ НАСТРОЙКИ
@router.callback_query(lambda c: c.data == "settings")
async def show_settings(callback: CallbackQuery):
    text = """
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
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ SAVE MODE НАСТРОЙКИ
@router.callback_query(lambda c: c.data == "savemode_settings")
async def savemode_settings(callback: CallbackQuery):
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
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="settings")
        ]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ АВТООТВЕТЧИК НАСТРОЙКИ
@router.callback_query(lambda c: c.data == "autoreply_settings")
async def autoreply_settings(callback: CallbackQuery):
    text = """
<b>🤖 Автоответчик</b>

▸ Автоматические ответы на сообщения
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Включить", callback_data="autoreply_on"),
            InlineKeyboardButton(text="🤖 Выключить", callback_data="autoreply_off")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="settings")
        ]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ НАЗАД В ГЛАВНОЕ МЕНЮ
@router.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    await callback.answer()
    # Передаём callback.message, а не просто message
    await start_command(callback.message)


# ✅ ЗАГЛУШКИ
@router.callback_query(lambda c: c.data == "savemode_on")
async def savemode_on(callback: CallbackQuery):
    await callback.answer("✅ SAVE MODE включен! Используй /savemode on")


@router.callback_query(lambda c: c.data == "savemode_off")
async def savemode_off(callback: CallbackQuery):
    await callback.answer("❌ SAVE MODE выключен! Используй /savemode off")


@router.callback_query(lambda c: c.data == "autoreply_on")
async def autoreply_on(callback: CallbackQuery):
    await callback.answer("🤖 Автоответчик включен! Используй /autoreply on")


@router.callback_query(lambda c: c.data == "autoreply_off")
async def autoreply_off(callback: CallbackQuery):
    await callback.answer("🤖 Автоответчик выключен! Используй /autoreply off")


# ✅ КОМАНДА /help
@router.message(Command("help"))
async def help_command(message: Message):
    await show_help(message)