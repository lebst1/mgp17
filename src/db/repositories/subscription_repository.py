from sqlalchemy import select, and_
from typing import Optional
from datetime import datetime, timedelta
from src.db.models import Subscription, Referral
from src.db.session import async_session
import logging

logger = logging.getLogger(__name__)


class SubscriptionRepository:

    @staticmethod
    async def get_or_create_subscription(user_id: int) -> Subscription:
        """Получить подписку или создать, если её нет"""
        async with async_session() as session:
            # ✅ ПРОВЕРЯЕМ, ЕСТЬ ЛИ УЖЕ ПОДПИСКА
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            subscription = result.scalar_one_or_none()

            # ✅ Если есть — возвращаем её
            if subscription:
                return subscription

            # ✅ Если нет — создаём новую с 1 днем бесплатно
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
    async def extend_subscription(user_id: int, days: int, reason: str = "referral") -> Optional[Subscription]:
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

    @staticmethod
    async def activate_referral(referrer_id: int, referred_id: int) -> bool:
        """Активировать реферальную ссылку"""
        async with async_session() as session:
            # Проверяем, не приглашает ли пользователь сам себя
            if referrer_id == referred_id:
                return False

            # Проверяем, не активировал ли уже этот пользователь рефералку
            existing = await session.scalar(
                select(Referral).where(Referral.referred_id == referred_id)
            )
            if existing:
                return False

            # Создаем запись о реферале
            referral = Referral(
                referrer_id=referrer_id,
                referred_id=referred_id,
                days_awarded=5
            )
            session.add(referral)

            # Продлеваем подписку рефереру
            await SubscriptionRepository.extend_subscription(
                user_id=referrer_id,
                days=5,
                reason="referral"
            )

            await session.commit()
            logger.info(f"✅ Реферал {referred_id} приглашен {referrer_id}")
            return True