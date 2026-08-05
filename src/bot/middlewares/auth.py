from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from src.db.repositories.user_repository import UserRepository
from src.config import settings
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки подписки"""

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

        if settings.REQUIRED_CHANNEL_ID and settings.REQUIRED_CHANNEL_URL:
            try:
                member = await self.bot.get_chat_member(
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
                        f"<a href='{settings.REQUIRED_CHANNEL_URL}'>{settings.REQUIRED_CHANNEL_URL}</a>\n\n"
                        f"После подписки нажмите «Проверить подписку».",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    return

            except Exception as e:
                logger.error(f"❌ Ошибка проверки подписки: {e}")

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