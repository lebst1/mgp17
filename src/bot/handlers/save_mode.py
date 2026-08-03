from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository

router = Router()


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
    await message.answer("📭 Функция в разработке")


@router.message(Command("search"))
async def search_messages(message: Message):
    """Поиск по сохраненным сообщениям"""
    query = message.text.replace("/search", "").strip()
    
    if not query:
        await message.answer("ℹ️ Введите текст для поиска: /search ваш запрос")
        return
    
    await message.answer(f"🔍 Поиск по запросу: <b>{query}</b>\n(Функция в разработке)", parse_mode="HTML")