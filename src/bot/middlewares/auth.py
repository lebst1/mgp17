from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from src.db.repositories.user_repository import UserRepository
from src.config import settings
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации пользователей и подписки на канал"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
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
        
        # ✅ ПРОВЕРКА ПОДПИСКИ НА КАНАЛ
        if settings.REQUIRED_CHANNEL_ID and settings.REQUIRED_CHANNEL_URL:
            try:
                bot: Bot = data.get('bot')
                if bot:
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
                        
                        await event.answer(
                            f"📢 <b>Подпишитесь на наш канал!</b>\n\n"
                            f"Для использования бота необходимо подписаться на канал:\n"
                            f"{settings.REQUIRED_CHANNEL_URL}\n\n"
                            f"После подписки нажмите «Проверить подписку».",
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                        return
                        
            except Exception as e:
                logger.error(f"❌ Ошибка проверки подписки: {e}")
        
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
        
        user = await UserRepository.get_by_id(user_id)
        
        if not user or not user.is_admin:
            if user_id != settings.OWNER_TELEGRAM_ID:
                await event.answer("⛔ Эта команда доступна только администраторам")
                return
        
        return await handler(event, data)