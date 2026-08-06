from datetime import datetime
from decimal import Decimal
from typing import Optional
import logging
import json

from sqlalchemy import select, func, and_

from src.config import settings
from src.db.models import (
    Payment, OrderStatus, PaymentProvider,
    Transaction, TransactionType, TransactionStatus,
    User, ReferralBonus, ReferralBonusStatus,
)
from src.db.session import async_session
from src.db.repositories.referral_repository import ReferralRepository
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)


class PaymentRepository:

    @staticmethod
    async def create(
        user_id: int,
        payment_id: str,
        amount: float,
        status: OrderStatus = OrderStatus.PENDING,
        provider: PaymentProvider = PaymentProvider.YOOKASSA,
        currency: str = "RUB",
        description: Optional[str] = None,
        provider_raw: Optional[dict] = None,
    ) -> Payment:
        try:
            async with async_session() as session:
                payment = Payment(
                    user_id=user_id,
                    payment_id=payment_id,
                    provider=provider,
                    amount=Decimal(str(amount)),
                    currency=currency,
                    status=status,
                    description=description,
                    provider_raw=json.dumps(provider_raw) if provider_raw else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(payment)
                await session.flush()

                tx = Transaction(
                    user_id=user_id,
                    type=TransactionType.SUBSCRIPTION,
                    status=TransactionStatus.PENDING,
                    amount=Decimal(str(amount)),
                    days_credited=settings.SUBSCRIPTION_DAYS,
                    payment_id=payment.id,
                    reference_id=payment_id,
                    description=description or f"Подписка на {settings.SUBSCRIPTION_DAYS} дней",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(tx)
                await session.commit()
                await session.refresh(payment)

                logger.info(
                    "💳 Платёж создан: %s user=%s amount=%s status=%s provider=%s",
                    payment_id, user_id, amount, status.value, provider.value,
                )
                return payment
        except Exception as e:
            SentryStub.capture_exception(
                e, context="PaymentRepository.create",
                user_id=user_id, payment_id=payment_id, amount=amount,
            )
            raise

    @staticmethod
    async def get_by_payment_id(payment_id: str) -> Optional[Payment]:
        try:
            async with async_session() as session:
                return await session.scalar(
                    select(Payment).where(Payment.payment_id == payment_id)
                )
        except Exception as e:
            SentryStub.capture_exception(
                e, context="PaymentRepository.get_by_payment_id",
                payment_id=payment_id,
            )
            raise

    @staticmethod
    async def has_any_successful_payment(user_id: int) -> bool:
        try:
            async with async_session() as session:
                count = await session.scalar(
                    select(func.count()).select_from(Payment).where(
                        and_(
                            Payment.user_id == user_id,
                            Payment.status == OrderStatus.PAID,
                        )
                    )
                ) or 0
                return count > 0
        except Exception as e:
            SentryStub.capture_exception(
                e, context="PaymentRepository.has_any_successful_payment",
                user_id=user_id,
            )
            raise

    @staticmethod
    async def mark_as_paid(
        payment_id: str,
        provider_raw: Optional[dict] = None,
    ) -> Optional[dict]:
        """Обрабатывает успешную оплату: PAID + extends subscription + реф. бонус."""
        try:
            async with async_session() as session:
                payment = await session.scalar(
                    select(Payment).where(Payment.payment_id == payment_id)
                )
                if not payment:
                    logger.error("Платёж не найден: %s", payment_id)
                    return None

                previous_status = payment.status
                if previous_status == OrderStatus.PAID:
                    logger.info("Платёж %s уже PAID (идемпотентность). Пропускаем.", payment_id)
                    return {"payment": payment, "first_payment": False, "referral_bonus": None}

                payment.status = OrderStatus.PAID
                payment.paid_at = datetime.utcnow()
                payment.updated_at = datetime.utcnow()
                if provider_raw:
                    existing = json.loads(payment.provider_raw) if payment.provider_raw else {}
                    existing.update(provider_raw)
                    payment.provider_raw = json.dumps(existing)

                user = await session.scalar(
                    select(User).where(User.telegram_id == payment.user_id)
                )
                if not user:
                    logger.error("Пользователь для платежа %s не найден: user=%s", payment_id, payment.user_id)
                    raise ValueError(f"User {payment.user_id} not found for payment {payment_id}")

                first_payment = not await PaymentRepository._has_paid_payments(session, user.telegram_id, exclude_pk=payment.id)

                user.extend_subscription(settings.SUBSCRIPTION_DAYS)

                tx = await session.scalar(
                    select(Transaction).where(
                        and_(
                            Transaction.payment_id == payment.id,
                            Transaction.type == TransactionType.SUBSCRIPTION,
                        )
                    )
                )
                if tx:
                    tx.status = TransactionStatus.COMPLETED
                    tx.completed_at = datetime.utcnow()
                    tx.updated_at = datetime.utcnow()

                referral_bonus = None
                if first_payment and user.referred_by is not None:
                    referral_bonus = await ReferralRepository.release_bonus_after_first_payment(
                        referred_id=user.telegram_id,
                        payment=payment,
                    )

                await session.commit()
                await session.refresh(payment)

                logger.info(
                    "💳✅ Платёж %s PAID. user=%s first_payment=%s referral_bonus=%s",
                    payment_id, user.telegram_id, first_payment,
                    referral_bonus.id if referral_bonus else None,
                )
                return {
                    "payment": payment,
                    "user": user,
                    "first_payment": first_payment,
                    "referral_bonus": referral_bonus,
                }
        except Exception as e:
            SentryStub.capture_exception(
                e, context="PaymentRepository.mark_as_paid",
                payment_id=payment_id,
            )
            raise

    @staticmethod
    async def _has_paid_payments(session, user_id: int, exclude_pk: Optional[int] = None) -> bool:
        stmt = select(func.count()).select_from(Payment).where(
            and_(
                Payment.user_id == user_id,
                Payment.status == OrderStatus.PAID,
            )
        )
        if exclude_pk is not None:
            stmt = stmt.where(Payment.id != exclude_pk)
        count = await session.scalar(stmt) or 0
        return count > 0

    @staticmethod
    async def mark_as_failed(
        payment_id: str,
        provider_raw: Optional[dict] = None,
    ) -> Optional[Payment]:
        try:
            async with async_session() as session:
                payment = await session.scalar(
                    select(Payment).where(Payment.payment_id == payment_id)
                )
                if not payment:
                    return None

                if payment.status in (OrderStatus.PAID, OrderStatus.REFUNDED):
                    logger.warning(
                        "Попытка пометить как FAILED платёж %s в статусе %s — игнорируем",
                        payment_id, payment.status.value,
                    )
                    return payment

                payment.status = OrderStatus.FAILED
                payment.updated_at = datetime.utcnow()
                if provider_raw:
                    existing = json.loads(payment.provider_raw) if payment.provider_raw else {}
                    existing.update(provider_raw)
                    payment.provider_raw = json.dumps(existing)

                tx = await session.scalar(
                    select(Transaction).where(
                        and_(
                            Transaction.payment_id == payment.id,
                            Transaction.type == TransactionType.SUBSCRIPTION,
                        )
                    )
                )
                if tx and tx.status == TransactionStatus.PENDING:
                    tx.status = TransactionStatus.FAILED
                    tx.updated_at = datetime.utcnow()

                await session.commit()
                await session.refresh(payment)
                logger.info("💳❌ Платёж %s -> FAILED", payment_id)
                return payment
        except Exception as e:
            SentryStub.capture_exception(
                e, context="PaymentRepository.mark_as_failed",
                payment_id=payment_id,
            )
            raise

    @staticmethod
    async def mark_as_refunded(
        payment_id: str,
        provider_raw: Optional[dict] = None,
    ) -> Optional[Payment]:
        try:
            async with async_session() as session:
                payment = await session.scalar(
                    select(Payment).where(Payment.payment_id == payment_id)
                )
                if not payment:
                    return None

                if payment.status == OrderStatus.REFUNDED:
                    return payment

                payment.status = OrderStatus.REFUNDED
                payment.refunded_at = datetime.utcnow()
                payment.updated_at = datetime.utcnow()
                if provider_raw:
                    existing = json.loads(payment.provider_raw) if payment.provider_raw else {}
                    existing.update(provider_raw)
                    payment.provider_raw = json.dumps(existing)

                bonus = await session.scalar(
                    select(ReferralBonus).where(
                        and_(
                            ReferralBonus.triggered_by_payment_id == payment.id,
                            ReferralBonus.status == ReferralBonusStatus.RELEASED,
                        )
                    )
                )
                if bonus:
                    bonus.status = ReferralBonusStatus.CANCELLED
                    bonus.cancelled_at = datetime.utcnow()
                    bonus.updated_at = datetime.utcnow()
                    logger.warning("🎁 Отменяем реф-бонус %s из-за возврата платежа %s", bonus.id, payment_id)

                tx = await session.scalar(
                    select(Transaction).where(
                        and_(
                            Transaction.payment_id == payment.id,
                            Transaction.type == TransactionType.SUBSCRIPTION,
                        )
                    )
                )
                if tx:
                    tx.status = TransactionStatus.CANCELLED
                    tx.updated_at = datetime.utcnow()

                refund_tx = Transaction(
                    user_id=payment.user_id,
                    type=TransactionType.REFUND,
                    status=TransactionStatus.COMPLETED,
                    amount=-payment.amount,
                    payment_id=payment.id,
                    reference_id=f"refund_{payment_id}",
                    description=f"Возврат платежа {payment_id}",
                    completed_at=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(refund_tx)

                await session.commit()
                await session.refresh(payment)
                logger.warning("💳↩️ Платёж %s -> REFUNDED", payment_id)
                return payment
        except Exception as e:
            SentryStub.capture_exception(
                e, context="PaymentRepository.mark_as_refunded",
                payment_id=payment_id,
            )
            raise

    @staticmethod
    async def update_status_only(payment_id: str, status: OrderStatus) -> Optional[Payment]:
        try:
            async with async_session() as session:
                payment = await session.scalar(
                    select(Payment).where(Payment.payment_id == payment_id)
                )
                if not payment:
                    return None
                payment.status = status
                payment.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(payment)
                return payment
        except Exception as e:
            SentryStub.capture_exception(
                e, context="PaymentRepository.update_status_only",
                payment_id=payment_id, status=status.value,
            )
            raise

    @staticmethod
    async def get_stats() -> dict:
        try:
            async with async_session() as session:
                total = await session.scalar(select(func.count()).select_from(Payment)) or 0
                paid = await session.scalar(
                    select(func.count()).select_from(Payment).where(Payment.status == OrderStatus.PAID)
                ) or 0
                failed = await session.scalar(
                    select(func.count()).select_from(Payment).where(Payment.status == OrderStatus.FAILED)
                ) or 0
                refunded = await session.scalar(
                    select(func.count()).select_from(Payment).where(Payment.status == OrderStatus.REFUNDED)
                ) or 0
                total_amount = await session.scalar(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == OrderStatus.PAID)
                ) or 0
            return {
                "total_payments": total,
                "paid_payments": paid,
                "failed_payments": failed,
                "refunded_payments": refunded,
                "total_amount": float(total_amount),
            }
        except Exception as e:
            SentryStub.capture_exception(e, context="PaymentRepository.get_stats")
            raise

    @staticmethod
    async def get_recent(limit: int = 20) -> list[Payment]:
        try:
            async with async_session() as session:
                result = await session.scalars(
                    select(Payment).order_by(Payment.created_at.desc()).limit(limit)
                )
                return list(result)
        except Exception as e:
            SentryStub.capture_exception(e, context="PaymentRepository.get_recent")
            raise
