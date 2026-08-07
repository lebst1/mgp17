from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging
import secrets
import string

from sqlalchemy import select, func

from src.config import settings
from src.db.models import User, ReferralBonus, ReferralBonusStatus, Transaction, TransactionType, TransactionStatus
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

        Если referral_code передан — начисляет бонусы СРАЗУ за регистрацию:
        - Реферал получает REFERRAL_BONUS_REFERRED_DAYS дней
        - Реферер получает REFERRAL_BONUS_REFERRER_DAYS дней
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
                            
                            # ✅ Проверяем, есть ли уже бонус
                            existing_bonus = await session.scalar(
                                select(ReferralBonus).where(ReferralBonus.referred_id == telegram_id)
                            )
                            
                            if not existing_bonus:
                                # ✅ Начисляем бонусы сразу за регистрацию
                                await UserRepository._grant_referral_bonuses(
                                    session, referrer_id, telegram_id
                                )
                            
                            logger.info(
                                "🔗 Привязка реферера при повторном визите: "
                                "user=%s -> referrer=%s",
                                telegram_id, referrer_id
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

                # ✅ Начисляем бонусы сразу за регистрацию
                if referrer_id:
                    await UserRepository._grant_referral_bonuses(
                        session, referrer_id, telegram_id
                    )

                logger.info(
                    "✅ Новый пользователь %s, trial %s дн. ref_code=%s referred_by=%s",
                    telegram_id, settings.TRIAL_DAYS,
                    user.referral_code, referrer_id,
                )
                return user, True
        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository.get_or_create",
                telegram_id=telegram_id, referral_code=referral_code,
            )
            raise

    @staticmethod
    async def _grant_referral_bonuses(session, referrer_id: int, referred_id: int) -> None:
        """Начисляет реферальные бонусы СРАЗУ за регистрацию."""
        try:
            existing = await session.scalar(
                select(ReferralBonus).where(ReferralBonus.referred_id == referred_id)
            )
            if existing:
                logger.info(f"Бонус для {referred_id} уже существует, пропускаем")
                return

            now = datetime.utcnow()
            
            bonus = ReferralBonus(
                referrer_id=referrer_id,
                referred_id=referred_id,
                status=ReferralBonusStatus.RELEASED,
                referrer_days=settings.REFERRAL_BONUS_REFERRER_DAYS,
                referred_days=settings.REFERRAL_BONUS_REFERRED_DAYS,
                released_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(bonus)
            await session.flush()

            referred_user = await session.scalar(
                select(User).where(User.telegram_id == referred_id)
            )
            if referred_user:
                referred_user.extend_subscription(settings.REFERRAL_BONUS_REFERRED_DAYS)
                referred_user.updated_at = now

            referrer = await session.scalar(
                select(User).where(User.telegram_id == referrer_id)
            )
            if referrer:
                referrer.extend_subscription(settings.REFERRAL_BONUS_REFERRER_DAYS)
                referrer.updated_at = now

            # ✅ ТРАНЗАКЦИИ
            tx_referred = Transaction(
                user_id=referred_id,
                type=TransactionType.REFERRAL_BONUS,
                status=TransactionStatus.COMPLETED,
                days_credited=settings.REFERRAL_BONUS_REFERRED_DAYS,
                referral_bonus_id=bonus.id,
                description=f"Реферальный бонус за регистрацию: +{settings.REFERRAL_BONUS_REFERRED_DAYS} дн.",
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(tx_referred)

            tx_referrer = Transaction(
                user_id=referrer_id,
                type=TransactionType.REFERRAL_BONUS,
                status=TransactionStatus.COMPLETED,
                days_credited=settings.REFERRAL_BONUS_REFERRER_DAYS,
                referral_bonus_id=bonus.id,
                description=f"Реферальный бонус за приглашение {referred_id}: +{settings.REFERRAL_BONUS_REFERRER_DAYS} дн.",
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(tx_referrer)

            await session.commit()

            # ✅ УВЕДОМЛЕНИЕ РЕФЕРАЛУ
            try:
                from src.bot import bot  # или передавай bot в функцию
                await bot.send_message(
                    chat_id=referred_id,
                    text=f"🎁 <b>Реферальный бонус!</b>\n\n"
                        f"Вы получили <b>+{settings.REFERRAL_BONUS_REFERRED_DAYS} день</b> подписки "
                        f"за регистрацию по реферальной ссылке! 🚀",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"❌ Не удалось отправить уведомление рефералу {referred_id}: {e}")
            
            # ✅ УВЕДОМЛЕНИЕ РЕФЕРЕРУ
            try:
                from src.bot import bot
                await bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎁 <b>Реферальный бонус!</b>\n\n"
                        f"Пользователь <code>{referred_id}</code> зарегистрировался по вашей ссылке!\n"
                        f"Вы получили <b>+{settings.REFERRAL_BONUS_REFERRER_DAYS} дня</b> подписки! 🚀",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"❌ Не удалось отправить уведомление рефереру {referrer_id}: {e}")

            logger.info(
                "🎁 Бонусы начислены за регистрацию: "
                "реферал +%s дн., реферер +%s дн.",
                settings.REFERRAL_BONUS_REFERRED_DAYS,
                settings.REFERRAL_BONUS_REFERRER_DAYS,
            )

        except Exception as e:
            SentryStub.capture_exception(
                e, context="UserRepository._grant_referral_bonuses",
                referrer_id=referrer_id, referred_id=referred_id,
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

        В новой логике начисление бонуса происходит сразу при регистрации.
        """
        try:
            if new_user_id == referrer_id:
                return False
            
            async with async_session() as session:
                # Проверяем, есть ли уже бонус
                existing = await session.scalar(
                    select(ReferralBonus).where(ReferralBonus.referred_id == new_user_id)
                )
                if existing:
                    return True
                
                # Начисляем бонусы
                await UserRepository._grant_referral_bonuses(
                    session, referrer_id, new_user_id
                )
                return True
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
                "total_referrals": total_referrals,
                "released_referrals": released_referrals,
                "held_referrals": held_referrals,
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