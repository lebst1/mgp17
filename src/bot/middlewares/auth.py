from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message
from src.db.repositories.user_repository import UserRepository
from src.config import settings
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if not hasattr(event, 'from_user') or not event.from_user:
            return await handler(event, data)
        
        user_id = event.from_user.id
        
        if not await UserRepository.check_access(user_id):
            await event.answer(
                "⛔ У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору."
            )
            return
        
        try:
            user, _ = await UserRepository.get_or_create(
                telegram_id=user_id,
                username=event.from_user.username,
                first_name=event.from_user.first_name,
                last_name=event.from_user.last_name
            )
            data['user'] = user
        except Exception as e:
            logger.error(f"Error creating user: {e}")
        
        return await handler(event, data)