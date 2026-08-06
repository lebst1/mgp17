from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging
import secrets
import string

from sqlalchemy import select, func

from src.config import settings
from src.db.models import User, ReferralBonus, ReferralBonusStatus
from src.db.session import async_session
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)


_REF_CODE_ALPHABET = string.ascii_uppercase + string.digits
_REF_CODE_LENGTH = 8


class UserRepository:
    """Репозиторий для работы с пользователями"""

    @staticmethod
    def _generate_referral_code(telegram_id: int) -> str:
        """Генерирует читаемый referral-код (не telegram_id напрямую)."""
        suffix = "".join(
            secrets.choice(_REF_CODE_ALPHABET)
            for _ in range(_REF_CODE_LENGTH)
        )
        prefix = str(telegram_id)[:3]
        return f"{prefix}{suffix}"

    @staticmethod
    async def resolve_referral_code(code: str) -> Optional[int]:
        """Определяет telegram_id реферера по коду (поддержка ?ref=CODE).

        Поддерживает как новый формат (A1B2C3D4), так и legacy (сырой telegram_id).
        """
        if not code:
            return None
        code = code.strip()
        if code.isdigit():
            return int(code)
        try:
            async with async_session() as session:
                user = await session.scalar(
                    select(User).where(User.referral_code == code)
                )
                return user.telegram_id if user else None
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.resolve_referral_code", code=code,
            )
            return None

    @staticmethod
    async def get_or_create(
        telegram_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        referral_code: Optional[str] = None,
    ) -> Tuple[User, bool]:
        """Создаёт или возвращает пользователя.

        Если referral_code передан — ТОЛЬКО привязывает referred_by и создаёт
        ReferralBonus в статусе HELD. Никаких бонусов за регистрацию не начисляет!
        Бонус выдаётся строго после ПЕРВОЙ успешной оплаты (см. PaymentRepository.mark_as_paid).
        """
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()

                if user:
                    changed = False
                    if username and user.username != username:
                        user.username = username
                        changed = True
                    if first_name and user.first_name != first_name:
                        user.first_name = first_name
                        changed = True
                    if last_name and user.last_name != last_name:
                        user.last_name = last_name
                        changed = True
                    if referral_code and user.referred_by is None:
                        referrer_id = await UserRepository.resolve_referral_code(referral_code)
                        if referrer_id and referrer_id != telegram_id:
                            user.referred_by = referrer_id
                            changed = True
                            from src.db.repositories.referral_repository import ReferralRepository as _RR
                            bonus = await _RR.bind_referrer(telegram_id, referral_code)
                            logger.info(
                                "🔗 Привязка реферера при повторном визите: "
                                "user=%s -> referrer=%s bonus_id=%s",
                                telegram_id, referrer_id, bonus.id if bonus else None,
                            )
                    if changed:
                        user.updated_at = datetime.utcnow()
                        await session.commit()
                        await session.refresh(user)
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
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                await session.flush()

                referrer_id = None
                if referral_code:
                    referrer_id = await UserRepository.resolve_referral_code(referral_code)
                    if referrer_id and referrer_id != telegram_id:
                        user.referred_by = referrer_id
                    else:
                        referrer_id = None

                await session.commit()
                await session.refresh(user)

                bonus_id = None
                if referrer_id:
                    from src.db.repositories.referral_repository import ReferralRepository as _RR
                    bonus = await _RR.bind_referrer(telegram_id, referral_code)
                    bonus_id = bonus.id if bonus else None

                logger.info(
                    "✅ Новый пользователь %s, trial %s дн. ref_code=%s referred_by=%s bonus_held=%s",
                    telegram_id, settings.TRIAL_DAYS,
                    user.referral_code, referrer_id, bonus_id is not None,
                )
                return user, True
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.get_or_create",
                telegram_id=telegram_id, referral_code=referral_code,
            )
            raise

    @staticmethod
    async def get_by_id(telegram_id: int) -> Optional[User]:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.get_by_id", telegram_id=telegram_id,
            )
            raise

    @staticmethod
    async def update_settings(telegram_id: int, **kwargs) -> Optional[User]:
        try:
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

                user.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(user)
                return user
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.update_settings", telegram_id=telegram_id, kwargs=kwargs,
            )
            raise

    @staticmethod
    async def extend_subscription(telegram_id: int, days: int) -> Optional[User]:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    return None

                user.extend_subscription(days)
                user.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(user)
                logger.info("✅ Подписка %s продлена на %s дн.", telegram_id, days)
                return user
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.extend_subscription",
                telegram_id=telegram_id, days=days,
            )
            raise

    @staticmethod
    async def revoke_subscription(telegram_id: int) -> Optional[User]:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    return None

                user.subscription_until = datetime.utcnow()
                user.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(user)
                logger.info("✅ Подписка %s отозвана", telegram_id)
                return user
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.revoke_subscription", telegram_id=telegram_id,
            )
            raise

    @staticmethod
    async def process_referral(new_user_id: int, referrer_id: int) -> bool:
        """DEPRECATED: оставлен для обратной совместимости.

        В новой логике начисление бонуса происходит только после первой оплаты.
        Этот метод сейчас ТОЛЬКО привязывает referred_by (без начисления дней).
        """
        try:
            if new_user_id == referrer_id:
                return False
            from src.db.repositories.referral_repository import ReferralRepository as _RR
            bonus = await _RR.bind_referrer(
                new_user_id, str(referrer_id),
            )
            return bonus is not None
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.process_referral",
                new_user_id=new_user_id, referrer_id=referrer_id,
            )
            return False

    @staticmethod
    async def get_subscription_stats() -> dict:
        try:
            now = datetime.utcnow()
            async with async_session() as session:
                total = await session.scalar(select(func.count()).select_from(User)) or 0
                active = await session.scalar(
                    select(func.count()).select_from(User).where(User.subscription_until > now)
                ) or 0
                expired = total - active
                total_referrals = await session.scalar(
                    select(func.count()).select_from(ReferralBonus)
                ) or 0
                released_referrals = await session.scalar(
                    select(func.count()).select_from(ReferralBonus).where(
                        ReferralBonus.status == ReferralBonusStatus.RELEASED
                    )
                ) or 0
                held_referrals = await session.scalar(
                    select(func.count()).select_from(ReferralBonus).where(
                        ReferralBonus.status == ReferralBonusStatus.HELD
                    )
                ) or 0
            return {
                "total_users": total,
                "active_subscriptions": active,
                "expired_subscriptions": expired,
                "total_referral_bonuses": int(total_referrals),
                "released_referral_bonuses": int(released_referrals),
                "held_referral_bonuses": int(held_referrals),
            }
        except Exception as e:
            SentryStub.capture_exception(e, context="UserRepository.get_subscription_stats")
            raise

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
