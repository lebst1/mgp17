from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.subscription_repository import SubscriptionRepository
from src.config import settings
import logging

logger = logging.getLogger(__name__)


def trim_text(text: str, max_len: int = 4000) -> str:
    """Обрезает текст до максимальной длины"""
    if len(text) > max_len:
        return text[:max_len] + "\n\n... (сообщение обрезано)"
    return text


class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации и подписки"""
    
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
            await event.answer("⛔ У вас нет доступа к этому боту.")
            return
        
        subscription = await SubscriptionRepository.get_active_subscription(user_id)
        if not subscription:
            subscription = await SubscriptionRepository.get_or_create_subscription(user_id)
            
            if subscription.trial_used:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Купить подписку 99₽",
                            callback_data="subscribe_buy"
                        )
                    ]
                ])
                
                text = trim_text(
                    "⏰ <b>Ваша подписка истекла!</b>\n\n"
                    "Чтобы продолжить пользоваться ботом:\n"
                    "• Купи подписку за 99₽/месяц\n\n"
                    "У тебя уже был пробный день."
                )
                
                await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
                return
            else:
                text = trim_text(
                    "🎁 <b>Добро пожаловать!</b>\n\n"
                    "Ты получил <b>1 день бесплатного</b> использования!\n"
                    "Наслаждайся всеми функциями бота.\n\n"
                    "После окончания пробного периода ты сможешь:\n"
                    "• Купить подписку за 99₽/месяц"
                )
                
                await event.answer(text, parse_mode="HTML")
        
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