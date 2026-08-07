from typing import Callable, Dict, Any, Awaitable
import logging

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from src.config import settings
from src.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# ✅ Разрешенные команды (доступны даже без подписки)
ALLOWED_COMMANDS = {
    "start",
    "profile",
    "buy",
    "pay",
    "ref",
    "subscribe",
    "admin",
    "cancel",
    "savemode",
    "help",
    "savemode_on",
    "savemode_off",
}

# ✅ Разрешенные callback'и (доступны даже без подписки)
ALLOWED_CALLBACK_PREFIXES = (
    "profile",
    "referral",
    "subscribe",
    "buy",
    "pay",
    "check_payment",
    "back_to_start",
    "copy_username",
    "edit_profile",
    "show_help",
    "important",
    "savemode",
    "savemode_toggle_on",
    "savemode_toggle_off",
    "savemode_stats",
)


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware для проверки активной подписки."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Определяем пользователя
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            return await handler(event, data)

        # Владелец всегда имеет доступ
        if user.id == settings.OWNER_TELEGRAM_ID:
            return await handler(event, data)

        # Получаем пользователя из БД
        db_user = data.get("user") or await UserRepository.get_by_id(user.id)
        if not db_user:
            return await handler(event, data)

        # Админы всегда имеют доступ
        if db_user.is_admin:
            return await handler(event, data)

        # Если подписка активна — пропускаем
        if db_user.has_active_subscription():
            return await handler(event, data)

        # Проверяем, разрешено ли это действие без подписки
        if self._is_allowed(event):
            return await handler(event, data)

        # Блокируем доступ
        text = (
            "⛔ <b>Подписка истекла</b>\n\n"
            "Продлите подписку, чтобы продолжить пользоваться ботом.\n\n"
            "Доступны команды:\n"
            "/start — главное меню\n"
            "/profile — личный кабинет\n"
            "/pay — купить подписку\n"
            "/ref — реферальная система\n"
            "/savemode — настройки SAVE MODE"
        )

        if isinstance(event, Message):
            await event.answer(text, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Подписка истекла. Продлите через /pay", show_alert=True)
            if event.message:
                await event.message.answer(text, parse_mode="HTML")

        return None

    @staticmethod
    def _is_allowed(event: TelegramObject) -> bool:
        """Проверяет, разрешено ли действие без подписки."""
        if isinstance(event, Message):
            if event.text and event.text.startswith("/"):
                command = event.text.split()[0].lstrip("/").split("@")[0].lower()
                return command in ALLOWED_COMMANDS
            return False

        if isinstance(event, CallbackQuery) and event.data:
            data = event.data
            # Проверяем точное совпадение
            if data in ALLOWED_CALLBACK_PREFIXES:
                return True
            # Проверяем начало строки
            return any(data.startswith(prefix) for prefix in ALLOWED_CALLBACK_PREFIXES)

        return False