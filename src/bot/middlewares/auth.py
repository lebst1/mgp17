from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from src.db.repositories.user_repository import UserRepository
from src.config import settings
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации пользователей"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Пропускаем, если нет пользователя (например, callback от бота)
        if not hasattr(event, 'from_user') or not event.from_user:
            return await handler(event, data)
        
        user_id = event.from_user.id
        
        # Проверяем доступ
        if not await UserRepository.check_access(user_id):
            await event.answer(
                "⛔ У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору."
            )
            return
        
        # Добавляем пользователя в БД
        try:
            user = await UserRepository.get_or_create(
                telegram_id=user_id,
                username=event.from_user.username,
                first_name=event.from_user.first_name,
                last_name=event.from_user.last_name
            )
            data['user'] = user
        except Exception as e:
            logger.error(f"Error creating user: {e}")
        
        return await handler(event, data)


class AdminMiddleware(BaseMiddleware):
    """Middleware для проверки прав администратора"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        
        # Проверяем, является ли пользователь админом
        user = await UserRepository.get_by_id(user_id)
        
        if not user or not user.is_admin:
            # Проверяем, может быть это владелец
            if user_id != settings.OWNER_TELEGRAM_ID:
                await event.answer("⛔ Эта команда доступна только администраторам")
                return
        
        return await handler(event, data)