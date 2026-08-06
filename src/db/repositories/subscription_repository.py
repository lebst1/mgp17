from sqlalchemy import select, and_
from typing import Optional
from datetime import datetime, timedelta
from src.db.models import Subscription
from src.db.session import async_session
import logging

logger = logging.getLogger(__name__)


class SubscriptionRepository:

    @staticmethod
    async def get_or_create_subscription(user_id: int) -> Subscription:
        """Получить подписку или создать, если её нет"""
        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            subscription = result.scalar_one_or_none()
            if subscription:
                return subscription
            new_sub = Subscription(
                user_id=user_id,
                subscription_type="trial",
                starts_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=1),
                trial_used=False,
                is_active=True
            )
            session.add(new_sub)
            await session.commit()
            await session.refresh(new_sub)
            logger.info(f"✅ Создана пробная подписка для {user_id}")
            return new_sub

    @staticmethod
    async def get_active_subscription(user_id: int) -> Optional[Subscription]:
        """Получить активную подписку"""
        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.is_active == True,
                    Subscription.expires_at > datetime.utcnow()
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def extend_subscription(user_id: int, days: int, reason: str = "admin") -> Optional[Subscription]:
        """Продлить подписку на N дней"""
        async with async_session() as session:
            subscription = await session.scalar(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            if not subscription:
                subscription = Subscription(
                    user_id=user_id,
                    subscription_type=reason,
                    starts_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(days=days),
                    is_active=True
                )
                session.add(subscription)
            else:
                if subscription.expires_at < datetime.utcnow():
                    subscription.expires_at = datetime.utcnow() + timedelta(days=days)
                else:
                    subscription.expires_at = subscription.expires_at + timedelta(days=days)
                subscription.is_active = True
                subscription.subscription_type = reason
            await session.commit()
            await session.refresh(subscription)
            logger.info(f"✅ Подписка {user_id} продлена на {days} дней ({reason})")
            return subscription