from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories import MessageRepository  # ✅ ПРАВИЛЬНЫЙ ИМПОРТ
from src.services.save_mode_business import SaveModeService

router = Router()
save_mode_service = SaveModeService()


@router.message(Command("savemode"))
async def toggle_savemode(message: Message):
    """Включить/выключить SAVE MODE для пользователя"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "ℹ️ Использование: /savemode on - включить, /savemode off - выключить"
        )
        return
    
    action = args[1].lower()
    
    if action not in ["on", "off"]:
        await message.answer("❌ Используйте 'on' или 'off'")
        return
    
    enabled = action == "on"
    
    # Обновляем настройки пользователя
    user = await UserRepository.update_settings(
        message.from_user.id,
        savemode_enabled=enabled
    )
    
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        return
    
    status = "включен" if enabled else "выключен"
    await message.answer(f"✅ SAVE MODE {status} для вашего аккаунта")


@router.message(Command("deleted"))
async def show_deleted(message: Message):
    """Показать последние удаленные сообщения"""
    messages = await MessageRepository.get_recent_deleted(
        user_id=message.from_user.id,
        limit=10
    )
    
    if not messages:
        await message.answer("📭 Нет удаленных сообщений")
        return
    
    text = "🗑 <b>Последние удаленные сообщения:</b>\n\n"
    for i, msg in enumerate(messages, 1):
        text += f"{i}. <b>Чат:</b> {msg.chat_title or msg.chat_id}\n"
        if msg.from_username:
            text += f"   <b>От:</b> @{msg.from_username}\n"
        if msg.text:
            preview = msg.text[:100] + "..." if len(msg.text) > 100 else msg.text
            text += f"   📝 {preview}\n"
        text += f"   🕐 {msg.saved_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("search"))
async def search_messages(message: Message):
    """Поиск по сохраненным сообщениям"""
    query = message.text.replace("/search", "").strip()
    
    if not query:
        await message.answer("ℹ️ Введите текст для поиска: /search ваш запрос")
        return
    
    results = await MessageRepository.search_messages(
        user_id=message.from_user.id,
        query=query,
        limit=10
    )
    
    if not results:
        await message.answer(f"🔍 Ничего не найдено по запросу: <b>{query}</b>", parse_mode="HTML")
        return
    
    text = f"🔍 <b>Результаты поиска:</b> '{query}'\n\n"
    for i, msg in enumerate(results, 1):
        text += f"{i}. <b>Чат:</b> {msg.chat_title or msg.chat_id}\n"
        if msg.text:
            preview = msg.text[:100] + "..." if len(msg.text) > 100 else msg.text
            text += f"   📝 {preview}\n"
        text += f"   🕐 {msg.saved_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await message.answer(text, parse_mode="HTML")