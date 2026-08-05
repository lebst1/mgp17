from sqlalchemy import select, and_, or_
from typing import Optional, List
from datetime import datetime, timedelta
from src.db.models import User, Subscription, Referral
from src.db.session import async_session
import logging

logger = logging.getLogger(__name__)


class SubscriptionRepository:
    """Репозиторий для работы с подписками"""
    
    @staticmethod
    async def get_or_create_subscription(user_id: int) -> Subscription:
        """Получить или создать подписку для пользователя"""
        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            subscription = result.scalar_one_or_none()
            
            if subscription:
                return subscription
            
            subscription = Subscription(
                user_id=user_id,
                subscription_type="trial",
                starts_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=1),
                trial_used=False,
                is_active=True
            )
            session.add(subscription)
            await session.commit()
            await session.refresh(subscription)
            logger.info(f"✅ Создана пробная подписка для {user_id} до {subscription.expires_at}")
            return subscription
    
    @staticmethod
    async def get_active_subscription(user_id: int) -> Optional[Subscription]:
        """Получить активную подписку пользователя"""
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
            logger.info(f"✅ Подписка {user_id} продлена на {days} дней (причина: {reason})")
            return subscription
    
    @staticmethod
    async def activate_referral(referrer_id: int, referred_id: int) -> bool:
        """Активировать реферальную связь"""
        async with async_session() as session:
            existing = await session.scalar(
                select(Referral).where(Referral.referred_id == referred_id)
            )
            if existing:
                return False
            
            if referrer_id == referred_id:
                return False
            
            referral = Referral(
                referrer_id=referrer_id,
                referred_id=referred_id,
                days_awarded=5
            )
            session.add(referral)
            
            await SubscriptionRepository.extend_subscription(
                user_id=referrer_id,
                days=5,
                reason="referral"
            )
            
            await session.commit()
            logger.info(f"✅ Реферал {referred_id} приглашен {referrer_id}")
            return True