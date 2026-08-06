from datetime import datetime
from typing import Optional
import logging

from sqlalchemy import select, func, and_

from src.config import settings
from src.db.models import (
    ReferralBonus, ReferralBonusStatus,
    User, Payment, OrderStatus,
    Transaction, TransactionType, TransactionStatus,
)
from src.db.session import async_session
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)


class ReferralRepository:

    @staticmethod
    async def bind_referrer(new_user_id: int, referrer_code: str) -> Optional[ReferralBonus]:
        """Привязывает реферера по коду при регистрации. Без начисления бонуса!

        Создаёт запись ReferralBonus со статусом HELD. Бонус будет зачислен
        только после ПЕРВОЙ успешной оплаты рефералом.
        """
        if not referrer_code:
            return None

        try:
            referrer_id = int(referrer_code) if referrer_code.isdigit() else None
        except (ValueError, TypeError):
            referrer_id = None

        if referrer_id is None or referrer_id == new_user_id:
            logger.warning("Невалидный реферальный код: %s для пользователя %s", referrer_code, new_user_id)
            return None

        try:
            async with async_session() as session:
                referrer = await session.scalar(
                    select(User).where(User.telegram_id == referrer_id)
                )
                new_user = await session.scalar(
                    select(User).where(User.telegram_id == new_user_id)
                )

                if not referrer or not new_user:
                    logger.warning("Реферер или пользователь не найден: %s -> %s", referrer_id, new_user_id)
                    return None

                if new_user.referred_by is not None:
                    logger.info("Пользователь %s уже привязан к рефереру %s", new_user_id, new_user.referred_by)
                    existing = await session.scalar(
                        select(ReferralBonus).where(ReferralBonus.referred_id == new_user_id)
                    )
                    return existing

                existing_bonus = await session.scalar(
                    select(ReferralBonus).where(ReferralBonus.referred_id == new_user_id)
                )
                if existing_bonus:
                    new_user.referred_by = referrer_id
                    await session.commit()
                    return existing_bonus

                new_user.referred_by = referrer_id

                bonus = ReferralBonus(
                    referrer_id=referrer_id,
                    referred_id=new_user_id,
                    status=ReferralBonusStatus.HELD,
                    referrer_days=settings.REFERRAL_BONUS_REFERRER_DAYS,
                    referred_days=settings.REFERRAL_BONUS_REFERRED_DAYS,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(bonus)
                await session.commit()
                await session.refresh(bonus)

                logger.info(
                    "🎁 Реферал привязан (HELD): %s от %s. Бонусы: реферер=%sдн, реферал=%sдн",
                    new_user_id, referrer_id, bonus.referrer_days, bonus.referred_days,
                )
                return bonus
        except Exception as e:
            SentryStub.capture_exception(
                e, context="ReferralRepository.bind_referrer",
                new_user_id=new_user_id, referrer_code=referrer_code,
            )
            return None

    @staticmethod
    async def release_bonus_after_first_payment(
        referred_id: int,
        payment: Payment,
    ) -> Optional[ReferralBonus]:
        """Выпускает (RELEASED) замороженный бонус после ПЕРВОЙ успешной оплаты.

        ВАЖНО: Вызывается только когда заказ переходит в статус PAID.
        Начисляет дни подписки рефереру и рефералу, создаёт транзакции.
        """
        try:
            async with async_session() as session:
                bonus = await session.scalar(
                    select(ReferralBonus).where(
                        and_(
                            ReferralBonus.referred_id == referred_id,
                            ReferralBonus.status == ReferralBonusStatus.HELD,
                        )
                    )
                )
                if not bonus:
                    logger.info("Нет HELD-бонуса для пользователя %s (возможно, уже выдан)", referred_id)
                    return None

                count_paid = await session.scalar(
                    select(func.count()).select_from(Payment).where(
                        and_(
                            Payment.user_id == referred_id,
                            Payment.status == OrderStatus.PAID,
                        )
                    )
                ) or 0

                if count_paid > 1:
                    logger.warning("У пользователя %s уже есть оплаченные заказы (%s), "
                                   "но бонус всё ещё HELD. Исправляю.", referred_id, count_paid)

                referrer = await session.scalar(
                    select(User).where(User.telegram_id == bonus.referrer_id)
                )
                referred_user = await session.scalar(
                    select(User).where(User.telegram_id == bonus.referred_id)
                )
                if not referrer or not referred_user:
                    logger.error("Пользователи для бонуса не найдены: %s", bonus)
                    return None

                bonus.status = ReferralBonusStatus.RELEASED
                bonus.released_at = datetime.utcnow()
                bonus.updated_at = datetime.utcnow()
                bonus.triggered_by_payment_id = payment.id

                if bonus.referred_days and bonus.referred_days > 0:
                    referred_user.extend_subscription(bonus.referred_days)

                if bonus.referrer_days and bonus.referrer_days > 0:
                    referrer.extend_subscription(bonus.referrer_days)

                await session.flush()

                tx_referred = None
                if bonus.referred_days and bonus.referred_days > 0:
                    tx_referred = Transaction(
                        user_id=referred_id,
                        type=TransactionType.REFERRAL_BONUS,
                        status=TransactionStatus.COMPLETED,
                        days_credited=bonus.referred_days,
                        referral_bonus_id=bonus.id,
                        reference_id=f"ref_referred_{bonus.id}",
                        description=f"Реферальный бонус (регистрация): +{bonus.referred_days} дн.",
                        completed_at=datetime.utcnow(),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    session.add(tx_referred)

                tx_referrer = None
                if bonus.referrer_days and bonus.referrer_days > 0:
                    tx_referrer = Transaction(
                        user_id=bonus.referrer_id,
                        type=TransactionType.REFERRAL_BONUS,
                        status=TransactionStatus.COMPLETED,
                        days_credited=bonus.referrer_days,
                        referral_bonus_id=bonus.id,
                        reference_id=f"ref_referrer_{bonus.id}",
                        description=f"Реферальный бонус (реферал {referred_id}): +{bonus.referrer_days} дн.",
                        completed_at=datetime.utcnow(),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    session.add(tx_referrer)

                await session.commit()
                await session.refresh(bonus)

                logger.info(
                    "🎁✅ Реферальный бонус РЕЛИЗНУТ: %s. "
                    "Реферер +%sдн (id=%s), Реферал +%sдн (id=%s). "
                    "Триггер-платёж: %s",
                    bonus.id,
                    bonus.referrer_days, bonus.referrer_id,
                    bonus.referred_days, bonus.referred_id,
                    payment.payment_id,
                )

                return bonus
        except Exception as e:
            SentryStub.capture_exception(
                e, context="ReferralRepository.release_bonus_after_first_payment",
                referred_id=referred_id, payment_id=payment.id if payment else None,
            )
            raise

    @staticmethod
    async def cancel_bonus(bonus_id: int, reason: str = "refund") -> Optional[ReferralBonus]:
        try:
            async with async_session() as session:
                bonus = await session.get(ReferralBonus, bonus_id)
                if not bonus:
                    return None
                bonus.status = ReferralBonusStatus.CANCELLED
                bonus.cancelled_at = datetime.utcnow()
                bonus.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(bonus)
                logger.warning("🎁❌ Реферальный бонус %s отменён: %s", bonus_id, reason)
                return bonus
        except Exception as e:
            SentryStub.capture_exception(
                e, context="ReferralRepository.cancel_bonus",
                bonus_id=bonus_id, reason=reason,
            )
            raise

    @staticmethod
    async def get_bonus_for_referred(referred_id: int) -> Optional[ReferralBonus]:
        try:
            async with async_session() as session:
                return await session.scalar(
                    select(ReferralBonus).where(ReferralBonus.referred_id == referred_id)
                )
        except Exception as e:
            SentryStub.capture_exception(
                e, context="ReferralRepository.get_bonus_for_referred",
                referred_id=referred_id,
            )
            raise

    @staticmethod
    async def get_referrer_stats(referrer_id: int) -> dict:
        try:
            async with async_session() as session:
                all_bonuses = list(await session.scalars(
                    select(ReferralBonus).where(ReferralBonus.referrer_id == referrer_id)
                ))
                total_referred = len(all_bonuses)
                released = [b for b in all_bonuses if b.status == ReferralBonusStatus.RELEASED]
                held = [b for b in all_bonuses if b.status == ReferralBonusStatus.HELD]
                cancelled = [b for b in all_bonuses if b.status == ReferralBonusStatus.CANCELLED]

                total_days_earned = sum(b.referrer_days for b in released)
                held_days = sum(b.referrer_days for b in held)

            return {
                "total_referred": total_referred,
                "released_count": len(released),
                "held_count": len(held),
                "cancelled_count": len(cancelled),
                "total_days_earned": total_days_earned,
                "held_days": held_days,
            }
        except Exception as e:
            SentryStub.capture_exception(
                e, context="ReferralRepository.get_referrer_stats",
                referrer_id=referrer_id,
            )
            raise

    @staticmethod
    async def list_referrer_bonuses(
        referrer_id: int,
        status: Optional[ReferralBonusStatus] = None,
        limit: int = 50,
    ) -> list[ReferralBonus]:
        try:
            async with async_session() as session:
                stmt = select(ReferralBonus).where(ReferralBonus.referrer_id == referrer_id)
                if status:
                    stmt = stmt.where(ReferralBonus.status == status)
                stmt = stmt.order_by(ReferralBonus.created_at.desc()).limit(limit)
                result = await session.scalars(stmt)
                return list(result)
        except Exception as e:
            SentryStub.capture_exception(
                e, context="ReferralRepository.list_referrer_bonuses",
                referrer_id=referrer_id,
            )
            raise
