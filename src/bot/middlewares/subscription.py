from typing import Callable, Dict, Any, Awaitable
import logging

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from src.config import settings
from src.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

ALLOWED_COMMANDS = {"start", "profile", "buy", "ref", "subscribe", "admin", "cancel", "savemode"}  # 👈 ДОБАВИЛИ savemode

ALLOWED_CALLBACK_PREFIXES = (
    "profile",
    "referral",
    "subscribe",
    "buy",
    "check_payment",
    "back_to_start",
    "copy_username",
    "edit_profile",
    "show_help",
    "important",
    "savemode",  # 👈 ДОБАВИЛИ
)


class SubscriptionMiddleware(BaseMiddleware):
    """Ограничивает доступ при истёкшей подписке."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            return await handler(event, data)

        if user.id == settings.OWNER_TELEGRAM_ID:
            return await handler(event, data)

        db_user = data.get("user") or await UserRepository.get_by_id(user.id)
        if not db_user:
            return await handler(event, data)

        if db_user.is_admin:
            return await handler(event, data)

        if db_user.has_active_subscription():
            return await handler(event, data)

        if self._is_allowed(event):
            return await handler(event, data)

        text = (
            "⛔ <b>Подписка истекла</b>\n\n"
            "Продлите подписку, чтобы продолжить пользоваться ботом.\n\n"
            "Доступны команды:\n"
            "/start — главное меню\n"
            "/profile — личный кабинет\n"
            "/buy — купить подписку\n"
            "/ref — реферальная система\n"
            "/savemode — включить/выключить SAVE MODE"
        )

        if isinstance(event, Message):
            await event.answer(text, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Подписка истекла. Продлите через /buy", show_alert=True)
            if event.message:
                await event.message.answer(text, parse_mode="HTML")

        return None

    @staticmethod
    def _is_allowed(event: TelegramObject) -> bool:
        if isinstance(event, Message):
            if event.text and event.text.startswith("/"):
                command = event.text.split()[0].lstrip("/").split("@")[0].lower()
                return command in ALLOWED_COMMANDS
            return False

        if isinstance(event, CallbackQuery) and event.data:
            data = event.data
            if data in ALLOWED_CALLBACK_PREFIXES:
                return True
            return any(data.startswith(prefix) for prefix in ALLOWED_CALLBACK_PREFIXES)

        return False