from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository
from src.config import settings

router = Router()


@router.message(Command("savemode"))
async def savemode_menu(message: Message):
    """Главное меню SAVE MODE с кнопками"""
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
    
    # Текущий статус SAVE MODE
    status_text = "✅ Включен" if user.savemode_enabled else "❌ Выключен"
    sub_status = "✅ Активна" if user.has_active_subscription() else "❌ Истекла"
    
    text = f"""
📝 <b>SAVE MODE</b>

Текущий статус: <b>{status_text}</b>
Подписка: <b>{sub_status}</b>

SAVE MODE позволяет сохранять удаленные и отредактированные сообщения, а также медиа-файлы из ваших бизнес-чатов.

💡 <b>Как работает:</b>
• Бот сохраняет все сообщения в выбранных чатах
• При удалении сообщения — вы получите уведомление с текстом
• При редактировании — вы увидите старую и новую версии
• Медиа-файлы сохраняются локально

⚠️ <b>Важно:</b> Для работы SAVE MODE требуется активная подписка!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Включить", callback_data="savemode_toggle_on"),
            InlineKeyboardButton(text="❌ Выключить", callback_data="savemode_toggle_off"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика сохранений", callback_data="savemode_stats"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start"),
        ]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "savemode_toggle_on")
async def savemode_toggle_on(callback: CallbackQuery):
    """Включение SAVE MODE с проверкой подписки"""
    user = await UserRepository.get_by_id(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # ✅ Проверка подписки
    if not user.has_active_subscription():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="subscribe_buy")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="savemode_back")],
        ])
        await callback.message.edit_text(
            "⛔ <b>Ошибка!</b>\n\n"
            "Для включения SAVE MODE требуется активная подписка.\n\n"
            "💰 <b>Подписка SafeSaverX:</b>\n"
            f"• {settings.SUBSCRIPTION_PRICE:.0f}₽ / {settings.SUBSCRIPTION_DAYS} дней\n"
            "• Сохранение всех сообщений\n"
            "• Уведомления об удалениях и правках\n"
            "• Сохранение медиа-файлов\n\n"
            "Нажмите кнопку ниже, чтобы купить подписку.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer("⛔ Требуется подписка!", show_alert=True)
        return
    
    # Включаем SAVE MODE
    user = await UserRepository.update_settings(callback.from_user.id, savemode_enabled=True)
    if user:
        await callback.message.edit_text(
            "✅ <b>SAVE MODE включен!</b>\n\n"
            "Теперь бот будет сохранять все сообщения в ваших бизнес-чатах.\n"
            "Вы будете получать уведомления при удалении и редактировании сообщений.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Статистика", callback_data="savemode_stats")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="savemode_back")],
            ]),
            parse_mode="HTML"
        )
        await callback.answer("✅ SAVE MODE включен!")
    else:
        await callback.answer("❌ Ошибка при включении", show_alert=True)


@router.callback_query(lambda c: c.data == "savemode_toggle_off")
async def savemode_toggle_off(callback: CallbackQuery):
    """Выключение SAVE MODE"""
    user = await UserRepository.update_settings(callback.from_user.id, savemode_enabled=False)
    if user:
        await callback.message.edit_text(
            "❌ <b>SAVE MODE выключен!</b>\n\n"
            "Бот больше не будет сохранять сообщения.\n"
            "Вы не будете получать уведомления об удалениях и правках.\n\n"
            "Чтобы снова включить SAVE MODE, используйте команду /savemode",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="savemode_back")],
            ]),
            parse_mode="HTML"
        )
        await callback.answer("❌ SAVE MODE выключен!")
    else:
        await callback.answer("❌ Ошибка при выключении", show_alert=True)


@router.callback_query(lambda c: c.data == "savemode_stats")
async def savemode_stats(callback: CallbackQuery):
    """Статистика сохраненных сообщений"""
    user = await UserRepository.get_by_id(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # Получаем статистику
    deleted = await MessageRepository.get_recent_deleted(user.telegram_id, limit=100)
    deleted_count = len(deleted)
    
    # Общее количество сохраненных сообщений
    from src.db.session import async_session
    from sqlalchemy import select, func
    from src.db.models import SavedMessage
    
    async with async_session() as session:
        total = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.user_id == user.telegram_id)
        ) or 0
        
        edited = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(
                SavedMessage.user_id == user.telegram_id,
                SavedMessage.is_edited == True
            )
        ) or 0
        
        media = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(
                SavedMessage.user_id == user.telegram_id,
                SavedMessage.media_path.isnot(None)
            )
        ) or 0
    
    status = "✅ Включен" if user.savemode_enabled else "❌ Выключен"
    
    text = f"""
📊 <b>Статистика SAVE MODE</b>

Текущий статус: <b>{status}</b>

📝 <b>Сохранено сообщений:</b> {total}
🗑️ <b>Удалено:</b> {deleted_count}
✏️ <b>Отредактировано:</b> {edited}
🖼️ <b>Медиа-файлов:</b> {media}

📅 <b>Последние удаленные сообщения:</b>
"""
    
    if deleted:
        for i, msg in enumerate(deleted[:5], 1):
            chat = msg.chat_title or f"Чат {msg.chat_id}"
            from_user = msg.from_username or msg.from_first_name or 'Аноним'
            text += f"{i}. {chat} — {from_user} ({msg.saved_at.strftime('%d.%m %H:%M')})\n"
    else:
        text += "Нет удаленных сообщений."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="savemode_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="savemode_back")],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data == "savemode_back")
async def savemode_back(callback: CallbackQuery):
    """Возврат в меню SAVE MODE"""
    await savemode_menu(callback.message)
    await callback.answer()


# ✅ Команда /savemode on (для обратной совместимости)
@router.message(Command("savemode_on"))
async def savemode_on_legacy(message: Message):
    """Legacy команда для включения"""
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
    
    if not user.has_active_subscription():
        await message.answer(
            "⛔ <b>Ошибка!</b>\n\n"
            f"Для включения SAVE MODE требуется активная подписка.\n\n"
            f"💰 Купить подписку: /buy\n"
            f"📋 Подробнее: /subscribe",
            parse_mode="HTML"
        )
        return
    
    user = await UserRepository.update_settings(message.from_user.id, savemode_enabled=True)
    if user:
        await message.answer("✅ SAVE MODE включен!")


@router.message(Command("savemode_off"))
async def savemode_off_legacy(message: Message):
    """Legacy команда для выключения"""
    user = await UserRepository.update_settings(message.from_user.id, savemode_enabled=False)
    if user:
        await message.answer("❌ SAVE MODE выключен!")


# ✅ Старые callback'и для совместимости
@router.callback_query(lambda c: c.data == "savemode_on")
async def savemode_on_old(callback: CallbackQuery):
    await savemode_toggle_on(callback)


@router.callback_query(lambda c: c.data == "savemode_off")
async def savemode_off_old(callback: CallbackQuery):
    await savemode_toggle_off(callback)


@router.callback_query(lambda c: c.data == "savemode_settings")
async def savemode_settings_old(callback: CallbackQuery):
    """Старый callback для совместимости"""
    await savemode_menu(callback.message)
    await callback.answer()