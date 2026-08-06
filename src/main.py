import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from src.bot.handlers import (
    start_router,
    savemode_router,
    admin_router,
    subscription_router,
    profile_router,
    referral_router,
)
from src.config import settings
from src.db.session import init_db
from src.db.models import (  # noqa: F401 — регистрация моделей для create_all
    Payment, Transaction, ReferralBonus,
)
from src.db.repositories.user_repository import UserRepository
from src.bot.middlewares.auth import AuthMiddleware
from src.bot.middlewares.subscription import SubscriptionMiddleware
from src.business_bot.handlers import router as business_router
from src.tasks import scheduled_cleanup
from src.utils.sentry import SentryStub
from src.services.webhook_server import start_webhook_server_async

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            "logs/bot.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        ),
    ],
)
logger = logging.getLogger(__name__)


async def setup_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher()

    dp.message.middleware(AuthMiddleware(bot))
    dp.callback_query.middleware(AuthMiddleware(bot))
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    dp.include_router(start_router)
    dp.include_router(profile_router)
    dp.include_router(referral_router)
    dp.include_router(subscription_router)
    dp.include_router(savemode_router)
    dp.include_router(business_router)
    dp.include_router(admin_router)

    return dp


async def main():
    logger.info("🚀 Запуск SafeSaverX...")
    logger.info(f"📌 Режим: {settings.TELEGRAM_MODE}")

    SentryStub.init(settings.SENTRY_DSN)
    if settings.SENTRY_DSN:
        logger.info("🔧 Sentry инициализирован (stub-mode)")

    try:
        await init_db()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        SentryStub.capture_exception(e, context="main.init_db")
        return

    if settings.OWNER_TELEGRAM_ID:
        try:
            owner, _ = await UserRepository.get_or_create(settings.OWNER_TELEGRAM_ID)
            if owner:
                await UserRepository.update_settings(settings.OWNER_TELEGRAM_ID, is_admin=True)
                logger.info(f"👤 Владелец бота: {settings.OWNER_TELEGRAM_ID}")
        except Exception as e:
            logger.error(f"❌ Ошибка создания владельца: {e}")
            SentryStub.capture_exception(e, context="main.owner_setup")

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = await setup_dispatcher(bot)

    allowed_updates = list(Update.model_fields.keys())
    logger.info(f"📋 Поддерживаемые апдейты: {len(allowed_updates)} типов")

    asyncio.create_task(scheduled_cleanup())
    logger.info("✅ Планировщик задач запущен")

    webhook_runner = await start_webhook_server_async()
    if webhook_runner is not None:
        logger.info("✅ Webhook-сервер платежей запущен")
    else:
        logger.warning("⚠️ Webhook-сервер не запущен (aiohttp не установлен или ошибка)")

    logger.info("✅ Бот запущен и готов к работе!")

    try:
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    except Exception as e:
        logger.error(f"❌ Ошибка при работе бота: {e}")
        SentryStub.capture_exception(e, context="main.dp_polling")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
