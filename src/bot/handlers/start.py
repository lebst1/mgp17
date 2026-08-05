from aiogram import Router
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
    CopyTextButton
)
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.business_repository import BusinessRepository
import os

router = Router()


# ✅ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ МЕНЮ
async def get_main_menu(user, has_business):
    text = f"""
<b>SafeSaverX</b>

👤 <b>Профиль</b>
▸ Статус: <b>{'активен' if user.is_active else 'неактивен'}</b>
▸ SAVE MODE: <b>{'включен' if user.savemode_enabled else 'выключен'}</b>

📌 <b>Как подключить бота:</b>
1. Нажми «📋 Скопировать юзернейм»
2. Открой Настройки Telegram → Редактирование профиля
3. Выбери «Автоматизация действий»
4. Вставь скопированный юзернейм
5. Дай ВСЕ разрешения!

<b>Что умеет бот:</b>
• Присылает уведомления, когда собеседник удаляет сообщение
• Присылает уведомления, когда собеседник редактирует сообщение
• Сохраняет фото, голосовые и видео
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
    InlineKeyboardButton(
        text="📋 Скопировать юзернейм",
        copy_text=CopyTextButton(
            text="@laosllebot"
        )
    )
],
[
    InlineKeyboardButton(text="✏️ Редактирование профиля", callback_data="edit_profile")
],
    [
        InlineKeyboardButton(
            text="❓ Описание команд",
            callback_data="show_help"
        ),
        InlineKeyboardButton(
            text="⭐ Важное",
            callback_data="important"
        )
    ],
    [
        InlineKeyboardButton(
            text="⚙️ Настройки",
            callback_data="settings"
        )
    ]
])
    
    return text, keyboard


# ✅ ОТПРАВКА МЕНЮ (С ФОТО ИЛИ БЕЗ)
async def send_main_menu(target, user, has_business):
    text, keyboard = await get_main_menu(user, has_business)
    photo_path = "assets/menu.jpg"
    
    if os.path.exists(photo_path):
        photo = FSInputFile(photo_path)
        await target.answer_photo(
            photo=photo,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


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
    
    await send_main_menu(message, user, has_business)



# ✅ РЕДАКТИРОВАНИЕ ПРОФИЛЯ
@router.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile(callback: CallbackQuery):
    await callback.answer()

    await callback.message.answer(
        """
<b>📌 Как подключить SafeSaverX</b>

1. Открой Telegram
2. Настройки
3. Редактирование профиля
4. Автоматизация действий
5. Добавь <code>@SafeSaverX_bot</code>
6. Выдай все разрешения

После подключения бот начнёт сохранять сообщения.
""",
        parse_mode="HTML"
    )


# ✅ ОПИСАНИЕ КОМАНД
@router.callback_query(lambda c: c.data == "show_help")
async def show_help(callback: CallbackQuery):
    text = """
❓ <b>Команды SafeSaverX</b>

/start — Главное меню
/help — Список команд
/settings — Настройки
/savemode on — Включить SAVE MODE
/savemode off — Выключить SAVE MODE
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    await callback.answer()


# ✅ ВАЖНОЕ
@router.callback_query(lambda c: c.data == "important")
async def important(callback: CallbackQuery):
    text = """
⭐ <b>Важное</b>

1️⃣ Дай ВСЕ разрешения на работу с сообщениями
2️⃣ Бот присылает уведомления при удалении/правке
3️⃣ Сохраняет фото, голосовые и видео
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    await callback.answer()


# ✅ НАСТРОЙКИ
@router.callback_query(lambda c: c.data == "settings")
async def show_settings(callback: CallbackQuery):
    text = """
⚙️ <b>Настройки</b>

▸ SAVE MODE — включить/выключить сохранение
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 SAVE MODE", callback_data="savemode_settings")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ]
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
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
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    await callback.answer()


# ✅ НАЗАД В ГЛАВНОЕ МЕНЮ
@router.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    await callback.answer()
    
    user = await UserRepository.get_by_id(callback.from_user.id)
    if not user:
        user = await UserRepository.get_or_create(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name
        )
    
    connections = await BusinessRepository.get_user_connections(callback.from_user.id)
    has_business = len(connections) > 0
    
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    await send_main_menu(callback.message, user, has_business)


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
    text = """
❓ <b>Команды SafeSaverX</b>

/start — Главное меню
/help — Список команд
/settings — Настройки
/savemode on — Включить SAVE MODE
/savemode off — Выключить SAVE MODE
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ КОМАНДА /settings
@router.message(Command("settings"))
async def settings_command(message: Message):
    text = """
⚙️ <b>Настройки</b>

▸ SAVE MODE — включить/выключить сохранение
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 SAVE MODE", callback_data="savemode_settings")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")