import hashlib
import hmac
import base64
import logging
from typing import Callable, Optional, Awaitable, Any
from functools import wraps

from src.config import settings
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)


class WebhookSignatureError(ValueError):
    pass


class YooKassaWebhookSignature:
    """Валидация подписи вебхуков ЮKassa по документации.

    Документация: https://yookassa.ru/developers/using-api/webhooks#hmac
    Формирование подписи: HMAC_SHA256(webhook_secret, raw_body)
    Сравнение: hmac.compare_digest(computed_mac, provided_mac)
    """

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.YOOKASSA_WEBHOOK_SECRET)

    @staticmethod
    def _compute_signature(raw_body: bytes, secret: str) -> str:
        mac = hmac.new(
            key=secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("ascii")

    @classmethod
    def verify(cls, raw_body: bytes, provided_signature: str, secret: Optional[str] = None) -> bool:
        if not raw_body or not provided_signature:
            logger.warning("Вебхук ЮKassa: отсутствует body или сигнатура")
            return False
        effective_secret = secret or settings.YOOKASSA_WEBHOOK_SECRET
        if not effective_secret:
            logger.warning("Вебхук ЮKassa: YOOKASSA_WEBHOOK_SECRET не настроен. "
                           "Пропускаем валидацию (НЕ БЕЗОПАСНО в проде!)")
            return True
        try:
            expected = cls._compute_signature(raw_body, effective_secret)
            is_valid = hmac.compare_digest(expected.strip(), provided_signature.strip())
            if not is_valid:
                logger.error(
                    "WEBHOOK SIGNATURE MISMATCH | provided=%s expected=%s",
                    provided_signature[:16] + "...",
                    expected[:16] + "...",
                )
                SentryStub.capture_message(
                    "YooKassa webhook signature mismatch",
                    level="error",
                    provided=provided_signature[:32],
                    expected=expected[:32],
                )
            return is_valid
        except Exception as e:
            SentryStub.capture_exception(e, context="YooKassaWebhookSignature.verify")
            return False


class StripeWebhookSignature:
    """Валидация подписи вебхуков Stripe по схеме v1 (tolerance на дрейф времени).

    Документация: https://stripe.com/docs/webhooks/signatures
    Заголовок: Stripe-Signature: t=timestamp,v1=hex_hmac_sha256(sig_secret, t.{timestamp}.{payload})
    """

    DEFAULT_TOLERANCE_SEC = 300

    @staticmethod
    def _parse_signature_header(header: str) -> tuple[Optional[str], dict[str, str]]:
        parts: dict[str, list[str]] = {}
        timestamp: Optional[str] = None
        for item in header.split(","):
            if "=" not in item:
                continue
            k, v = item.split("=", 1)
            if k == "t":
                timestamp = v
            else:
                parts.setdefault(k, []).append(v)
        return timestamp, parts

    @classmethod
    def verify(
        cls,
        raw_body: bytes,
        stripe_signature_header: str,
        secret: str,
        tolerance_sec: int = DEFAULT_TOLERANCE_SEC,
    ) -> bool:
        import time as _time
        if not raw_body or not stripe_signature_header or not secret:
            return False
        try:
            timestamp, schemes = cls._parse_signature_header(stripe_signature_header)
            if not timestamp or "v1" not in schemes:
                return False
            signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
            expected = hmac.new(
                key=secret.encode("utf-8"),
                msg=signed_payload,
                digestmod=hashlib.sha256,
            ).hexdigest()
            signatures = schemes.get("v1", [])
            matched = any(hmac.compare_digest(expected, sig) for sig in signatures)
            if not matched:
                logger.error("STRIPE WEBHOOK SIGNATURE MISMATCH")
                SentryStub.capture_message("Stripe webhook signature mismatch", level="error")
                return False
            if tolerance_sec > 0:
                try:
                    ts_int = int(timestamp)
                    if abs(_time.time() - ts_int) > tolerance_sec:
                        logger.error("STRIPE WEBHOOK timestamp outside tolerance")
                        return False
                except (TypeError, ValueError):
                    return False
            return True
        except Exception as e:
            SentryStub.capture_exception(e, context="StripeWebhookSignature.verify")
            return False


def require_yookassa_signature(handler: Callable[..., Awaitable[Any]]):
    """aiohttp/FastAPI-style middleware декоратор для валидации сигнатуры ЮKassa."""

    @wraps(handler)
    async def wrapper(request, *args, **kwargs):
        try:
            raw_body = await request.read() if hasattr(request, "read") else b""
            provided = (
                request.headers.get("HTTP_CONTENT_SIGNATURE")
                or request.headers.get("Content-Signature")
                or request.headers.get("X-Content-Signature")
                or ""
            )
            if not YooKassaWebhookSignature.verify(raw_body, provided):
                SentryStub.capture_message(
                    "Rejected YooKassa webhook: invalid signature",
                    level="warning",
                    headers=dict(request.headers) if hasattr(request, "headers") else None,
                )
                from aiohttp import web
                return web.Response(status=401, text="Invalid signature")
            return await handler(request, *args, **kwargs)
        except Exception as e:
            SentryStub.capture_exception(e, context="require_yookassa_signature.middleware")
            from aiohttp import web
            return web.Response(status=500, text="Internal error")

    return wrapper
