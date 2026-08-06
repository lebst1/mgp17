import logging
from typing import Optional
from uuid import uuid4

from src.config import settings
from src.db.repositories.payment_repository import PaymentRepository

logger = logging.getLogger(__name__)


class YooKassaService:
    """Сервис интеграции с ЮKassa."""

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY)

    @staticmethod
    def _configure():
        from yookassa import Configuration

        Configuration.account_id = settings.YOOKASSA_SHOP_ID
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

    @staticmethod
    async def create_payment(user_id: int) -> Optional[dict]:
        if not YooKassaService.is_configured():
            logger.warning("ЮKassa не настроена")
            return None

        try:
            from yookassa import Payment

            YooKassaService._configure()

            idempotence_key = str(uuid4())
            payment = Payment.create(
                {
                    "amount": {
                        "value": f"{settings.SUBSCRIPTION_PRICE:.2f}",
                        "currency": "RUB",
                    },
                    "confirmation": {
                        "type": "redirect",
                        "return_url": f"https://t.me/{settings.BOT_USERNAME}",
                    },
                    "capture": True,
                    "description": f"Подписка SafeSaverX на {settings.SUBSCRIPTION_DAYS} дней",
                    "metadata": {"user_id": str(user_id)},
                },
                idempotence_key,
            )

            await PaymentRepository.create(
                user_id=user_id,
                payment_id=payment.id,
                amount=settings.SUBSCRIPTION_PRICE,
                status=payment.status,
            )

            return {
                "payment_id": payment.id,
                "payment_url": payment.confirmation.confirmation_url,
                "status": payment.status,
            }
        except Exception as e:
            logger.error(f"❌ Ошибка создания платежа ЮKassa: {e}")
            return None

    @staticmethod
    async def check_payment(payment_id: str) -> Optional[dict]:
        if not YooKassaService.is_configured():
            return None

        try:
            from yookassa import Payment

            YooKassaService._configure()
            payment = Payment.find_one(payment_id)

            db_payment = await PaymentRepository.get_by_payment_id(payment_id)
            if db_payment and db_payment.status != payment.status:
                await PaymentRepository.update_status(payment_id, payment.status)

            return {
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.status == "succeeded",
                "user_id": int(payment.metadata.get("user_id", 0)) if payment.metadata else 0,
            }
        except Exception as e:
            logger.error(f"❌ Ошибка проверки платежа {payment_id}: {e}")
            return None
