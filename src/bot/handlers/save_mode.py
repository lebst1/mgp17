from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository

router = Router()


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


@router.message(Command("edits"))
async def show_edits(message: Message):
    """Показать последние отредактированные сообщения"""
    await message.answer("✏️ Функция в разработке")


@router.message(Command("media"))
async def show_media(message: Message):
    """Показать последние сохраненные медиа"""
    await message.answer("🖼️ Функция в разработке")


@router.message(Command("savemode_settings"))
async def savemode_settings(message: Message):
    """Настройки SAVE MODE"""
    await message.answer("⚙️ Настройки SAVE MODE\n\n/savemode on - включить\n/savemode off - выключить")


@router.message(Command("savemode"))
async def toggle_savemode(message: Message):
    """Включить/выключить SAVE MODE"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("ℹ️ Использование: /savemode on - включить, /savemode off - выключить")
        return
    
    action = args[1].lower()
    
    if action not in ["on", "off"]:
        await message.answer("❌ Используйте 'on' или 'off'")
        return
    
    enabled = action == "on"
    user = await UserRepository.update_settings(message.from_user.id, savemode_enabled=enabled)
    
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        return
    
    status = "включен" if enabled else "выключен"
    await message.answer(f"✅ SAVE MODE {status} для вашего аккаунта")