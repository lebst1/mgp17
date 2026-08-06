from datetime import datetime
from decimal import Decimal
from typing import Optional
import logging
import json

from sqlalchemy import select, func

from src.db.models import (
    Transaction, TransactionType, TransactionStatus,
)
from src.db.session import async_session
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)


class TransactionRepository:

    @staticmethod
    async def create(
        user_id: int,
        type: TransactionType,
        status: TransactionStatus = TransactionStatus.PENDING,
        amount: Optional[float] = None,
        days_credited: Optional[int] = None,
        payment_id: Optional[int] = None,
        referral_bonus_id: Optional[int] = None,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Transaction:
        try:
            async with async_session() as session:
                tx = Transaction(
                    user_id=user_id,
                    type=type,
                    status=status,
                    amount=Decimal(str(amount)) if amount is not None else None,
                    days_credited=days_credited,
                    payment_id=payment_id,
                    referral_bonus_id=referral_bonus_id,
                    reference_id=reference_id,
                    description=description,
                    metadata_=json.dumps(metadata) if metadata else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                if status == TransactionStatus.COMPLETED:
                    tx.completed_at = datetime.utcnow()
                session.add(tx)
                await session.commit()
                await session.refresh(tx)
                logger.info(
                    "💼 Транзакция создана: id=%s user=%s type=%s status=%s",
                    tx.id, user_id, type.value, status.value,
                )
                return tx
        except Exception as e:
            SentryStub.capture_exception(
                e, context="TransactionRepository.create",
                user_id=user_id, type=type.value,
            )
            raise

    @staticmethod
    async def get_by_id(tx_id: int) -> Optional[Transaction]:
        try:
            async with async_session() as session:
                return await session.get(Transaction, tx_id)
        except Exception as e:
            SentryStub.capture_exception(e, context="TransactionRepository.get_by_id", tx_id=tx_id)
            raise

    @staticmethod
    async def get_by_reference(reference_id: str) -> Optional[Transaction]:
        try:
            async with async_session() as session:
                return await session.scalar(
                    select(Transaction).where(Transaction.reference_id == reference_id)
                )
        except Exception as e:
            SentryStub.capture_exception(
                e, context="TransactionRepository.get_by_reference",
                reference_id=reference_id,
            )
            raise

    @staticmethod
    async def update_status(
        tx_id: int,
        status: TransactionStatus,
        metadata: Optional[dict] = None,
    ) -> Optional[Transaction]:
        try:
            async with async_session() as session:
                tx = await session.get(Transaction, tx_id)
                if not tx:
                    return None
                tx.status = status
                tx.updated_at = datetime.utcnow()
                if status == TransactionStatus.COMPLETED and not tx.completed_at:
                    tx.completed_at = datetime.utcnow()
                if metadata:
                    existing = json.loads(tx.metadata_) if tx.metadata_ else {}
                    existing.update(metadata)
                    tx.metadata_ = json.dumps(existing)
                await session.commit()
                await session.refresh(tx)
                logger.info("💼 Транзакция %s -> %s", tx_id, status.value)
                return tx
        except Exception as e:
            SentryStub.capture_exception(
                e, context="TransactionRepository.update_status",
                tx_id=tx_id, status=status.value,
            )
            raise

    @staticmethod
    async def list_user_transactions(
        user_id: int,
        limit: int = 50,
        type: Optional[TransactionType] = None,
    ) -> list[Transaction]:
        try:
            async with async_session() as session:
                stmt = select(Transaction).where(Transaction.user_id == user_id)
                if type:
                    stmt = stmt.where(Transaction.type == type)
                stmt = stmt.order_by(Transaction.created_at.desc()).limit(limit)
                result = await session.scalars(stmt)
                return list(result)
        except Exception as e:
            SentryStub.capture_exception(
                e, context="TransactionRepository.list_user_transactions",
                user_id=user_id,
            )
            raise

    @staticmethod
    async def get_stats() -> dict:
        try:
            async with async_session() as session:
                total = await session.scalar(select(func.count()).select_from(Transaction)) or 0
                completed = await session.scalar(
                    select(func.count()).select_from(Transaction).where(
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                ) or 0
                total_amount = await session.scalar(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.status == TransactionStatus.COMPLETED,
                        Transaction.amount.isnot(None),
                    )
                ) or 0
            return {
                "total_transactions": total,
                "completed_transactions": completed,
                "total_amount": float(total_amount),
            }
        except Exception as e:
            SentryStub.capture_exception(e, context="TransactionRepository.get_stats")
            raise
