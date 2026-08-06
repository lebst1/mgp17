import asyncio
import logging
from typing import Optional

from src.config import settings
from src.services.yookassa_service import YooKassaService
from src.services.webhook_security import (
    YooKassaWebhookSignature,
    StripeWebhookSignature,
)
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)


def _import_aiohttp():
    try:
        from aiohttp import web
        return web
    except Exception:
        logger.warning("aiohttp не установлен. Вебхуки ЮKassa/Stripe недоступны.")
        return None


async def _health_check(_request):
    web = _import_aiohttp()
    if not web:
        return None
    return web.json_response({"status": "ok", "service": "mgp17-payment-webhooks"})


def _yookassa_signature_from_request(request) -> str:
    return (
        request.headers.get("HTTP_CONTENT_SIGNATURE")
        or request.headers.get("Content-Signature")
        or request.headers.get("X-Content-Signature")
        or request.headers.get("X-Yookassa-Signature")
        or ""
    )


async def _handle_yookassa_webhook(request):
    web = _import_aiohttp()
    if not web:
        return web.Response(status=500, text="aiohttp not installed") if web else None
    try:
        raw_body = await request.read()
        sig_header = _yookassa_signature_from_request(request)
        result = await YooKassaService.handle_webhook(raw_body, sig_header)
        status_code = int(result.get("status", 200))
        body = dict(result)
        body.pop("status", None)
        return web.json_response(body, status=status_code)
    except Exception as e:
        SentryStub.capture_exception(e, context="webhook._handle_yookassa_webhook")
        return web.json_response({"ok": False, "error": "handler_error"}, status=500)


async def _handle_stripe_webhook(request):
    web = _import_aiohttp()
    if not web:
        return None
    try:
        raw_body = await request.read()
        sig_header = request.headers.get("Stripe-Signature", "")
        stripe_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        if not StripeWebhookSignature.verify(raw_body, sig_header, stripe_secret or ""):
            SentryStub.capture_message("Rejected Stripe webhook: invalid signature", level="warning")
            return web.Response(status=401, text="Invalid signature")
        return web.json_response({"ok": True, "note": "stripe_webhook_received_stub"})
    except Exception as e:
        SentryStub.capture_exception(e, context="webhook._handle_stripe_webhook")
        return web.json_response({"ok": False, "error": "handler_error"}, status=500)


def create_webhook_app():
    """Создаёт aiohttp Application с вебхук-эндпоинтами и middleware валидации.

    Endpoints:
      GET  /health              — liveness-проба
      POST /webhooks/yookassa    — вебхуки ЮKassa (HMAC-валидация подписи)
      POST /webhooks/stripe      — вебхуки Stripe (v1-scheme + tolerance)

    Middleware:
      1. log_and_validate_middleware   — логирование + Content-Type проверка
      2. json_errors_middleware        — перехват исключений в JSON-ответ + Sentry
    """
    web = _import_aiohttp()
    if not web:
        raise RuntimeError("aiohttp required for webhook server: pip install aiohttp")

    @web.middleware
    async def log_and_validate_middleware(request, handler):
        try:
            if request.method == "POST":
                ctype = request.headers.get("Content-Type", "")
                if "application/json" not in ctype.lower():
                    logger.warning(
                        "Webhook %s: неожиданный Content-Type: %s",
                        request.path, ctype,
                    )
            return await handler(request)
        except Exception as e:
            SentryStub.capture_exception(
                e, context="webhook.log_and_validate_mw",
                path=request.path, method=request.method,
            )
            return web.json_response(
                {"ok": False, "error": "internal_error"}, status=500,
            )

    @web.middleware
    async def json_errors_middleware(request, handler):
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except Exception as exc:
            SentryStub.capture_exception(
                exc, context="webhook.json_errors_mw", path=request.path,
            )
            return web.json_response(
                {"ok": False, "error": "server_error", "detail": str(exc)[:120]},
                status=500,
            )

    app = web.Application(middlewares=[
        log_and_validate_middleware,
        json_errors_middleware,
    ])

    app.router.add_get("/health", _health_check)
    app.router.add_post("/webhooks/yookassa", _handle_yookassa_webhook)
    app.router.add_post("/webhooks/stripe", _handle_stripe_webhook)

    return app


async def start_webhook_server_async(
    host: Optional[str] = None,
    port: Optional[int] = None,
):
    """Запускает aiohttp-сервер с вебхук-эндпоинтами (параллельно боту)."""
    web = _import_aiohttp()
    if not web:
        logger.warning(
            "aiohttp не установлен. Webhook-сервер НЕ запущен. "
            "Установите: pip install aiohttp"
        )
        return None

    effective_host = host if host is not None else settings.PAYMENT_WEBHOOK_HOST
    effective_port = port if port is not None else settings.PAYMENT_WEBHOOK_PORT

    try:
        app = create_webhook_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, effective_host, effective_port)
        await site.start()
        logger.info(
            "📡 Webhook-сервер: http://%s:%s | "
            "endpoints: POST /webhooks/yookassa, POST /webhooks/stripe | health: GET /health",
            effective_host, effective_port,
        )
        return runner
    except Exception as e:
        SentryStub.capture_exception(
            e, context="start_webhook_server_async",
            host=effective_host, port=effective_port,
        )
        logger.exception("❌ Не удалось запустить webhook-сервер: %s", e)
        return None
