from datetime import datetime
from decimal import Decimal
from typing import Optional
import logging

from sqlalchemy import select, func

from src.db.models import Payment
from src.db.session import async_session

logger = logging.getLogger(__name__)


class PaymentRepository:

    @staticmethod
    async def create(user_id: int, payment_id: str, amount: float, status: str = "pending") -> Payment:
        async with async_session() as session:
            payment = Payment(
                user_id=user_id,
                payment_id=payment_id,
                amount=Decimal(str(amount)),
                status=status,
                created_at=datetime.utcnow(),
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
            logger.info(f"💳 Платёж создан: {payment_id} user={user_id} amount={amount}")
            return payment

    @staticmethod
    async def get_by_payment_id(payment_id: str) -> Optional[Payment]:
        async with async_session() as session:
            return await session.scalar(
                select(Payment).where(Payment.payment_id == payment_id)
            )

    @staticmethod
    async def update_status(payment_id: str, status: str) -> Optional[Payment]:
        async with async_session() as session:
            payment = await session.scalar(
                select(Payment).where(Payment.payment_id == payment_id)
            )
            if not payment:
                return None
            payment.status = status
            await session.commit()
            await session.refresh(payment)
            logger.info(f"💳 Платёж {payment_id} -> {status}")
            return payment

    @staticmethod
    async def get_stats() -> dict:
        async with async_session() as session:
            total = await session.scalar(select(func.count()).select_from(Payment)) or 0
            succeeded = await session.scalar(
                select(func.count()).select_from(Payment).where(Payment.status == "succeeded")
            ) or 0
            total_amount = await session.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "succeeded")
            ) or 0
        return {
            "total_payments": total,
            "succeeded_payments": succeeded,
            "total_amount": float(total_amount),
        }

    @staticmethod
    async def get_recent(limit: int = 20) -> list[Payment]:
        async with async_session() as session:
            result = await session.scalars(
                select(Payment).order_by(Payment.created_at.desc()).limit(limit)
            )
            return list(result)
