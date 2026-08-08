import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import settings
from src.bot.middlewares.auth import AuthMiddleware
from src.bot.middlewares.subscription import SubscriptionMiddleware
from src.bot.handlers import (
    start_router,
    profile_router,
    referral_router,
    subscription_router,
    admin_router,
    save_mode_router,
)
from src.business_bot.handlers import router as business_router  # 👈 ДОБАВЛЯЕМ
from src.db.session import init_db
from src.utils.sentry import SentryStub

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Основная функция запуска бота"""
    try:
        # Инициализация БД
        await init_db()
        logger.info("✅ База данных инициализирована")

        # Инициализация бота
        bot = Bot(
            token=settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        # Подключаем мидлвари
        dp.message.middleware(AuthMiddleware(bot))
        dp.callback_query.middleware(AuthMiddleware(bot))

        dp.message.middleware(SubscriptionMiddleware())
        dp.callback_query.middleware(SubscriptionMiddleware())

        # Подключаем роутеры
        dp.include_router(start_router)
        dp.include_router(profile_router)
        dp.include_router(referral_router)
        dp.include_router(subscription_router)
        dp.include_router(admin_router)
        dp.include_router(save_mode_router)
        dp.include_router(business_router)  # 👈 ДОБАВЛЯЕМ

        logger.info(f"🚀 Бот запущен: @{settings.BOT_USERNAME}")
        logger.info(f"👤 Владелец: {settings.OWNER_TELEGRAM_ID}")

        await dp.start_polling(bot)

    except Exception as e:
        SentryStub.capture_exception(e, context="main")
        logger.critical(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())