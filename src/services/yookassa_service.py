import logging
import json
from typing import Optional
from uuid import uuid4

from src.config import settings
from src.db.models import OrderStatus, PaymentProvider
from src.db.repositories.payment_repository import PaymentRepository
from src.services.webhook_security import YooKassaWebhookSignature
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)


YOOKASSA_STATUS_TO_ORDER_STATUS = {
    "pending": OrderStatus.PENDING,
    "waiting_for_capture": OrderStatus.PENDING,
    "succeeded": OrderStatus.PAID,
    "canceled": OrderStatus.FAILED,
    "cancelled": OrderStatus.FAILED,
}


class YooKassaService:
    """Сервис интеграции с ЮKassa.

    Правила:
    - Секретные ключи ТОЛЬКО на сервере (config из .env)
    - Все запросы идут через create_payment / check_payment / handle_webhook
    - Валидация HMAC-подписи вебхуков строго по документации ЮKassa
    - Идемпотентность: повторные webhook-события не дублируют начисления
    """

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY)

    @staticmethod
    def _configure():
        try:
            from yookassa import Configuration
            Configuration.account_id = settings.YOOKASSA_SHOP_ID
            Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
        except Exception as e:
            SentryStub.capture_exception(e, context="YooKassaService._configure")
            raise

    @staticmethod
    async def create_payment(
        user_id: int,
        return_url: Optional[str] = None,
        description: Optional[str] = None,
        amount: Optional[float] = None,
    ) -> Optional[dict]:
        """Создаёт платёж в ЮKassa и сохраняет запись в БД (PENDING)."""
        if not YooKassaService.is_configured():
            logger.warning("ЮKassa не настроена (YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY не заданы)")
            return None

        try:
            from yookassa import Payment
            YooKassaService._configure()

            effective_amount = amount if amount is not None else settings.SUBSCRIPTION_PRICE
            effective_description = description or (
                f"Подписка SafeSaverX на {settings.SUBSCRIPTION_DAYS} дней"
            )
            effective_return_url = return_url or (
                f"https://t.me/{settings.BOT_USERNAME.lstrip('@')}"
                if settings.BOT_USERNAME else "https://t.me/"
            )

            idempotence_key = str(uuid4())
            SentryStub.add_breadcrumb(
                category="yookassa",
                message=f"create_payment user={user_id}",
                level="info",
                idempotence_key=idempotence_key,
                amount=effective_amount,
            )

            payment = Payment.create(
                {
                    "amount": {
                        "value": f"{effective_amount:.2f}",
                        "currency": "RUB",
                    },
                    "confirmation": {
                        "type": "redirect",
                        "return_url": effective_return_url,
                    },
                    "capture": True,
                    "description": effective_description,
                    "metadata": {
                        "user_id": str(user_id),
                        "source": "SafeSaverX",
                    },
                },
                idempotence_key,
            )

            await PaymentRepository.create(
                user_id=user_id,
                payment_id=payment.id,
                amount=effective_amount,
                status=YOOKASSA_STATUS_TO_ORDER_STATUS.get(payment.status, OrderStatus.PENDING),
                provider=PaymentProvider.YOOKASSA,
                currency="RUB",
                description=effective_description,
                provider_raw={"idempotence_key": idempotence_key},
            )

            return {
                "payment_id": payment.id,
                "payment_url": payment.confirmation.confirmation_url,
                "status": payment.status,
                "order_status": YOOKASSA_STATUS_TO_ORDER_STATUS.get(
                    payment.status, OrderStatus.PENDING
                ).value,
                "amount": effective_amount,
            }
        except Exception as e:
            SentryStub.capture_exception(
                e, context="YooKassaService.create_payment", user_id=user_id,
            )
            logger.exception("❌ Ошибка создания платежа ЮKassa (user=%s): %s", user_id, e)
            return None

    @staticmethod
    async def check_payment(payment_id: str) -> Optional[dict]:
        """Запрашивает статус платежа у ЮKassa и обновляет БД.

        Если платёж оплачен — вызывает mark_as_paid (продлевает подписку,
        начисляет реферальный бонус при первой оплате).
        """
        if not YooKassaService.is_configured():
            return None
        if not payment_id:
            return None

        try:
            from yookassa import Payment
            YooKassaService._configure()

            payment = Payment.find_one(payment_id)
            yk_status = payment.status
            order_status = YOOKASSA_STATUS_TO_ORDER_STATUS.get(yk_status, OrderStatus.PENDING)

            user_id = 0
            try:
                if payment.metadata and "user_id" in payment.metadata:
                    user_id = int(payment.metadata["user_id"])
            except (TypeError, ValueError):
                user_id = 0

            result_data = {
                "payment_id": payment.id,
                "status": yk_status,
                "order_status": order_status.value,
                "paid": order_status == OrderStatus.PAID,
                "user_id": user_id,
                "amount": float(payment.amount.value) if getattr(payment, "amount", None) else 0.0,
            }

            if order_status == OrderStatus.PAID:
                mark_result = await PaymentRepository.mark_as_paid(
                    payment_id=payment_id,
                    provider_raw={"last_check": yk_status},
                )
                if mark_result:
                    result_data["first_payment"] = mark_result.get("first_payment", False)
                    result_data["referral_bonus_released"] = bool(
                        mark_result.get("referral_bonus")
                    )
                    result_data["referrer_bonus_days"] = (
                        mark_result["referral_bonus"].referrer_days
                        if mark_result.get("referral_bonus") else 0
                    )
                    result_data["referred_bonus_days"] = (
                        mark_result["referral_bonus"].referred_days
                        if mark_result.get("referral_bonus") else 0
                    )
            elif order_status == OrderStatus.FAILED:
                await PaymentRepository.mark_as_failed(
                    payment_id=payment_id,
                    provider_raw={"last_check": yk_status},
                )
            else:
                await PaymentRepository.update_status_only(payment_id, order_status)

            return result_data
        except Exception as e:
            SentryStub.capture_exception(
                e, context="YooKassaService.check_payment", payment_id=payment_id,
            )
            logger.exception("❌ Ошибка проверки платежа %s: %s", payment_id, e)
            return None

    @staticmethod
    async def handle_webhook(
        raw_body: bytes,
        content_signature_header: str,
    ) -> dict:
        """Обработчик вебхука ЮKassa с валидацией подписи.

        Возвращает dict с ключами:
          - ok: bool
          - status: str (HTTP-статус для ответа)
          - event: str (тип события)
          - payment_id: Optional[str]
          - handled: bool (было ли применено изменение)
          - error: Optional[str]

        Валидация подписи — строго по документации ЮKassa (HMAC-SHA256,
        сравнение через hmac.compare_digest для защиты от timing-атак).
        """
        event_type: Optional[str] = None
        payment_id: Optional[str] = None
        handled = False
        error: Optional[str] = None
        http_status = 200

        try:
            if not YooKassaWebhookSignature.verify(raw_body, content_signature_header):
                logger.error("WEBHOOK ЮKASSA: неверная подпись. Отклонено.")
                return {
                    "ok": False,
                    "status": 401,
                    "event": None,
                    "payment_id": None,
                    "handled": False,
                    "error": "invalid_signature",
                }

            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as je:
                SentryStub.capture_exception(je, context="YooKassaService.handle_webhook.json")
                return {
                    "ok": False, "status": 400, "event": None,
                    "payment_id": None, "handled": False,
                    "error": "invalid_json_body",
                }

            event_type = payload.get("event")
            obj = payload.get("object", {}) or {}
            payment_id = obj.get("id")
            yk_status = obj.get("status")

            SentryStub.add_breadcrumb(
                category="yookassa",
                message=f"webhook event={event_type} payment={payment_id} status={yk_status}",
                level="info",
            )

            if event_type == "payment.succeeded":
                result = await PaymentRepository.mark_as_paid(
                    payment_id=payment_id,
                    provider_raw={"webhook": payload},
                )
                handled = result is not None
                logger.info(
                    "💳 WEBHOOK payment.succeeded: %s handled=%s first_payment=%s",
                    payment_id, handled,
                    result.get("first_payment") if result else None,
                )
            elif event_type in ("payment.canceled", "payment.cancelled"):
                await PaymentRepository.mark_as_failed(
                    payment_id=payment_id,
                    provider_raw={"webhook": payload},
                )
                handled = True
                logger.info("💳 WEBHOOK payment.canceled: %s", payment_id)
            elif event_type == "refund.succeeded":
                parent_payment_id = (obj.get("payment_id") if isinstance(obj, dict) else None)
                if parent_payment_id:
                    await PaymentRepository.mark_as_refunded(
                        payment_id=parent_payment_id,
                        provider_raw={"refund_webhook": payload},
                    )
                    handled = True
                    logger.warning("💳 WEBHOOK refund.succeeded for payment: %s", parent_payment_id)
            elif event_type == "payment.waiting_for_capture":
                await PaymentRepository.update_status_only(payment_id, OrderStatus.PENDING)
                handled = True
            else:
                logger.info("WEBHOOK: неизвестное событие %s — пропускаем", event_type)

            return {
                "ok": True,
                "status": http_status,
                "event": event_type,
                "payment_id": payment_id,
                "handled": handled,
                "error": error,
            }
        except Exception as e:
            SentryStub.capture_exception(
                e, context="YooKassaService.handle_webhook",
                event_type=event_type, payment_id=payment_id,
            )
            logger.exception("❌ Ошибка обработки вебхука ЮKassa: %s", e)
            return {
                "ok": False, "status": 500,
                "event": event_type, "payment_id": payment_id,
                "handled": False, "error": str(e),
            }
