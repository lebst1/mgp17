from datetime import datetime, timedelta
from typing import Optional
import logging
import uuid

from src.config import settings
from src.db.models import User
from src.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class SubscriptionRepository:
    """Обёртка над полями подписки в модели User."""

    @staticmethod
    async def get_or_create_subscription(user_id: int) -> User:
        user, _ = await UserRepository.get_or_create(user_id)
        return user

    @staticmethod
    async def get_active_subscription(user_id: int) -> Optional[User]:
        user = await UserRepository.get_by_id(user_id)
        if user and user.has_active_subscription():
            return user
        return None

    @staticmethod
    async def extend_subscription(user_id: int, days: int, reason: str = "admin") -> Optional[User]:
        user = await UserRepository.extend_subscription(user_id, days)
        if user:
            logger.info(f"✅ Подписка {user_id} +{days} дн. ({reason})")
        return user

    @staticmethod
    def get_days_left(user: User) -> int:
        info = user.get_subscription_info()
        return info["days_left"]
