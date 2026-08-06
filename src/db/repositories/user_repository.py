from datetime import datetime, timedelta
from typing import Optional
import logging

from sqlalchemy import select, func

from src.config import settings
from src.db.models import User
from src.db.session import async_session

logger = logging.getLogger(__name__)


class UserRepository:
    """Репозиторий для работы с пользователями"""

    @staticmethod
    def _generate_referral_code(telegram_id: int) -> str:
        return str(telegram_id)

    @staticmethod
    async def get_or_create(
        telegram_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
    ) -> tuple[User, bool]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user:
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                if last_name:
                    user.last_name = last_name
                await session.commit()
                return user, False

            now = datetime.utcnow()
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                subscription_until=now + timedelta(days=settings.TRIAL_DAYS),
                referral_code=UserRepository._generate_referral_code(telegram_id),
                referrals_count=0,
                referral_days_earned=0,
                referral_reward_claimed=False,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"✅ Новый пользователь {telegram_id}, trial {settings.TRIAL_DAYS} дн.")
            return user, True

    @staticmethod
    async def get_by_id(telegram_id: int) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def update_settings(telegram_id: int, **kwargs) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                return None

            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            await session.commit()
            await session.refresh(user)
            return user

    @staticmethod
    async def extend_subscription(telegram_id: int, days: int) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return None

            user.extend_subscription(days)
            await session.commit()
            await session.refresh(user)
            logger.info(f"✅ Подписка {telegram_id} продлена на {days} дн.")
            return user

    @staticmethod
    async def revoke_subscription(telegram_id: int) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return None

            user.subscription_until = datetime.utcnow()
            await session.commit()
            await session.refresh(user)
            logger.info(f"✅ Подписка {telegram_id} отозвана")
            return user

    @staticmethod
    async def process_referral(new_user_id: int, referrer_id: int) -> bool:
        if new_user_id == referrer_id:
            return False

        async with async_session() as session:
            new_user = await session.scalar(
                select(User).where(User.telegram_id == new_user_id)
            )
            referrer = await session.scalar(
                select(User).where(User.telegram_id == referrer_id)
            )

            if not new_user or not referrer:
                return False

            if new_user.referral_reward_claimed or new_user.referred_by is not None:
                return False

            new_user.referred_by = referrer_id
            new_user.referral_reward_claimed = True
            new_user.extend_subscription(1)

            referrer.extend_subscription(3)
            referrer.referrals_count = (referrer.referrals_count or 0) + 1
            referrer.referral_days_earned = (referrer.referral_days_earned or 0) + 3

            await session.commit()
            logger.info(f"✅ Реферал: {new_user_id} от {referrer_id}")
            return True

    @staticmethod
    async def get_subscription_stats() -> dict:
        now = datetime.utcnow()
        async with async_session() as session:
            total = await session.scalar(select(func.count()).select_from(User)) or 0
            active = await session.scalar(
                select(func.count()).select_from(User).where(User.subscription_until > now)
            ) or 0
            expired = total - active
            total_referrals = await session.scalar(
                select(func.coalesce(func.sum(User.referrals_count), 0))
            ) or 0
        return {
            "total_users": total,
            "active_subscriptions": active,
            "expired_subscriptions": expired,
            "total_referrals": int(total_referrals),
        }

    @staticmethod
    async def check_access(telegram_id: int) -> bool:
        if settings.PUBLIC_MODE:
            if telegram_id in settings.BANNED_USERS:
                return False

            user = await UserRepository.get_by_id(telegram_id)
            return user.is_active if user else True

        if settings.ALLOWED_USERS and telegram_id not in settings.ALLOWED_USERS:
            return False
        return True
