import logging
from typing import Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)


class SentryStub:
    """Sentry integration stub.

    In production replace with real Sentry SDK init:
        import sentry_sdk
        sentry_sdk.init(dsn="...", traces_sample_rate=1.0)
    """

    _initialized = False
    _dsn: Optional[str] = None

    @classmethod
    def init(cls, dsn: Optional[str] = None, **kwargs) -> None:
        cls._dsn = dsn
        cls._initialized = bool(dsn)
        if cls._initialized:
            logger.info("Sentry initialized with DSN (stub mode — no real events sent)")
        else:
            logger.warning("Sentry DSN not provided — running in stub mode")

    @staticmethod
    def capture_exception(exception: BaseException, **extra) -> None:
        try:
            logger.error(
                "[SENTRY STUB] capture_exception: %s: %s | extra=%s",
                type(exception).__name__,
                str(exception),
                extra,
                exc_info=True,
            )
        except Exception:
            pass

    @staticmethod
    def capture_message(message: str, level: str = "info", **extra) -> None:
        try:
            log_fn = getattr(logger, level, logger.info)
            log_fn("[SENTRY STUB] capture_message [%s]: %s | extra=%s", level, message, extra)
        except Exception:
            pass

    @staticmethod
    def set_tag(key: str, value: Any) -> None:
        logger.debug("[SENTRY STUB] set_tag: %s=%s", key, value)

    @staticmethod
    def set_user(user_info: dict) -> None:
        logger.debug("[SENTRY STUB] set_user: %s", user_info)

    @staticmethod
    def add_breadcrumb(category: str, message: str, level: str = "info", **data) -> None:
        logger.debug(
            "[SENTRY STUB] breadcrumb [%s/%s]: %s | data=%s",
            category,
            level,
            message,
            data,
        )


sentry = SentryStub()


def with_sentry(fn):
    """Decorator that auto-captures exceptions via Sentry stub."""

    @wraps(fn)
    async def async_wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            SentryStub.capture_exception(e, function=fn.__name__, args=args, kwargs=kwargs)
            raise

    @wraps(fn)
    def sync_wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            SentryStub.capture_exception(e, function=fn.__name__, args=args, kwargs=kwargs)
            raise

    import asyncio
    if asyncio.iscoroutinefunction(fn):
        return async_wrapper
    return sync_wrapper
