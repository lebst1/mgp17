from aiogram import Router, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.business_repository import BusinessRepository
from src.config import settings
import os
import logging

logger = logging.getLogger(__name__)

router = Router()


# ✅ ОБРАБОТЧИК ПРОВЕРКИ ПОДПИСКИ
@router.callback_query(lambda c: c.data == "check_subscription")
async def check_subscription(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    
    try:
        member = await bot.get_chat_member(
            chat_id=settings.REQUIRED_CHANNEL_ID,
            user_id=user_id
        )
        
        if member.status in ['left', 'kicked']:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📢 Подписаться на канал",
                        url=settings.REQUIRED_CHANNEL_URL
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Проверить подписку",
                        callback_data="check_subscription"
                    )
                ]
            ])
            await callback.message.edit_text(
                f"📢 <b>Вы ещё не подписаны на канал!</b>\n\n"
                f"Подпишитесь и нажмите «Проверить подписку».",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                "✅ <b>Спасибо за подписку!</b>\n\n"
                "Теперь вы можете пользоваться ботом.\n"
                "Напишите /start, чтобы начать.",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"❌ Ошибка проверки подписки: {e}")
        await callback.answer("❌ Ошибка проверки, попробуйте позже.", show_alert=True)
    
    await callback.answer()


async def get_main_menu(user, has_business):
    text = f"""
<b>SafeSaverX</b>

👤 <b>Профиль</b>
▸ Статус: <b>{'активен' if user.is_active else 'неактивен'}</b>
▸ SAVE MODE: <b>{'включен' if user.savemode_enabled else 'выключен'}</b>
▸ Business: <b>{'подключен' if has_business else 'не подключен'}</b>

📌 <b>Как подключить бота:</b>
1. Нажми «📋 Скопировать юзернейм»
2. Открой Настройки Telegram → Редактирование профиля
3. Выбери «Автоматизация действий»
4. Вставь скопированный юзернейм
5. Дай ВСЕ разрешения!

<b>Что умеет бот:</b>
• Присылает уведомления, когда собеседник удаляет сообщение
• Присылает уведомления, когда собеседник редактирует сообщение
• Сохраняет сгорающие фото, голосовые и видео
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Скопировать юзернейм", callback_data="copy_username")
        ],
        [
            InlineKeyboardButton(text="✏️ Редактирование профиля", callback_data="edit_profile")
        ],
        [
            InlineKeyboardButton(text="❓ Описание команд", callback_data="show_help"),
            InlineKeyboardButton(text="⭐ Важное", callback_data="important")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
        ]
    ])
    
    if settings.REQUIRED_CHANNEL_URL:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="📢 Наш канал", url=settings.REQUIRED_CHANNEL_URL)
        ])
    
    return text, keyboard


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


@router.message(Command("start"))
async def start_command(message: Message):

    if settings.REQUIRED_CHANNEL_ID and settings.REQUIRED_CHANNEL_URL:
        try:
            member = await message.bot.get_chat_member(
                settings.REQUIRED_CHANNEL_ID,
                message.from_user.id
            )

            if member.status in ["left", "kicked"]:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📢 Подписаться",
                                url=settings.REQUIRED_CHANNEL_URL
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="🔄 Проверить подписку",
                                callback_data="check_subscription"
                            )
                        ]
                    ]
                )

                await message.answer(
                    "📢 Для использования бота подпишитесь на канал.",
                    reply_markup=keyboard
                )
                return

        except Exception as e:
            logger.error(f"Ошибка проверки подписки: {e}")
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


@router.callback_query(lambda c: c.data == "copy_username")
async def copy_username(callback: CallbackQuery):
    await callback.answer(
        text="✅ @SafeSaverX_bot скопирован!\n\nОткрой Настройки → Редактирование профиля → Автоматизация действий и вставь юзернейм.",
        show_alert=True
    )


@router.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile(callback: CallbackQuery):
    await callback.answer(
        text="📌 Открой Настройки Telegram → Редактирование профиля → Автоматизация действий → вставь @SafeSaverX_bot",
        show_alert=True
    )


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


@router.callback_query(lambda c: c.data == "important")
async def important(callback: CallbackQuery):
    text = """
⭐ <b>Важное</b>

1️⃣ Дай ВСЕ разрешения на работу с сообщениями
2️⃣ Бот присылает уведомления при удалении/правке
3️⃣ Сохраняет сгорающие фото, голосовые и видео
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


@router.callback_query(lambda c: c.data == "savemode_on")
async def savemode_on(callback: CallbackQuery):
    await callback.answer("✅ SAVE MODE включен! Используй /savemode on")


@router.callback_query(lambda c: c.data == "savemode_off")
async def savemode_off(callback: CallbackQuery):
    await callback.answer("❌ SAVE MODE выключен! Используй /savemode off")


@router.message(Command("help"))
async def help_command(message: Message):
    await show_help(message)


@router.message(Command("settings"))
async def settings_command(message: Message):
    await show_settings(message)