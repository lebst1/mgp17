from aiogram import Router, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.business_repository import BusinessRepository

router = Router()


# ✅ ГЛАВНОЕ МЕНЮ (СТАРТ)
@router.message(Command("start"))
async def start_command(message: Message):
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        user = await UserRepository.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
    
    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    has_business = len(connections) > 0
    
    text = f"""
<b>SafeSaverX</b>

👤 <b>Профиль</b>
▸ Статус: <b>{'активен' if user.is_active else 'неактивен'}</b>
▸ SAVE MODE: <b>{'включен' if user.savemode_enabled else 'выключен'}</b>
▸ Business: <b>{'подключен' if has_business else 'не подключен'}</b>

📌 <b>Важно!</b> Дайте все разрешения на работу с сообщениями.

• Бот присылает уведомления, когда собеседник удаляет или редактирует сообщения.
• Может сохранять сгорающие фото, голосовые и видео.
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Скопировать юзернейм", callback_data="copy_username")
        ],
        [
            InlineKeyboardButton(text="✏️ Редактирование профиля", url="tg://settings")
        ],
        [
            InlineKeyboardButton(text="❓ Описание команд", callback_data="show_help"),
            InlineKeyboardButton(text="⭐ Важное", callback_data="important")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
        ]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ КОПИРОВАНИЕ ЮЗЕРНЕЙМ
@router.callback_query(lambda c: c.data == "copy_username")
async def copy_username(callback: CallbackQuery):
    await callback.answer(
        text="✅ @SafeSaverX_bot скопирован!",
        show_alert=True
    )


# ✅ ОПИСАНИЕ КОМАНД
@router.callback_query(lambda c: c.data == "show_help")
async def show_help(callback: CallbackQuery):
    text = """
❓ <b>Описание команд</b>

/start — 🚀 Главное меню
/help — 📖 Список команд
/settings — ⚙️ Настройки
/savemode — 📝 Вкл/Выкл SAVE MODE
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ ВАЖНОЕ
@router.callback_query(lambda c: c.data == "important")
async def important(callback: CallbackQuery):
    text = """
⭐ <b>Важное</b>

• Дайте все разрешения на работу с сообщениями
• Бот присылает уведомления при удалении/правке
• Сохраняет сгорающие фото, голосовые и видео
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ НАСТРОЙКИ
@router.callback_query(lambda c: c.data == "settings")
async def show_settings(callback: CallbackQuery):
    text = """
⚙️ <b>Настройки</b>

▸ SAVE MODE — сохранение сообщений
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 SAVE MODE", callback_data="savemode_settings")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ SAVE MODE НАСТРОЙКИ
@router.callback_query(lambda c: c.data == "savemode_settings")
async def savemode_settings(callback: CallbackQuery):
    text = """
📝 <b>SAVE MODE</b>

▸ Включить / Выключить сохранение
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


# ✅ НАЗАД В ГЛАВНОЕ МЕНЮ
@router.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    await callback.answer()
    await start_command(callback.message)


# ✅ ЗАГЛУШКИ
@router.callback_query(lambda c: c.data == "savemode_on")
async def savemode_on(callback: CallbackQuery):
    await callback.answer("✅ SAVE MODE включен! Используй /savemode on")


@router.callback_query(lambda c: c.data == "savemode_off")
async def savemode_off(callback: CallbackQuery):
    await callback.answer("❌ SAVE MODE выключен! Используй /savemode off")


# ✅ КОМАНДА /help
@router.message(Command("help"))
async def help_command(message: Message):
    await show_help(message)


# ✅ КОМАНДА /settings
@router.message(Command("settings"))
async def settings_command(message: Message):
    await show_settings(message)