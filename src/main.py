import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from src.config import settings
from src.db.session import init_db
from src.db.repositories.user_repository import UserRepository
from src.bot.middlewares.auth import AuthMiddleware
from src.bot.handlers import start_router, savemode_router
from src.business_bot.handlers import router as business_router
from src.tasks import scheduled_cleanup

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            'logs/bot.log',
            maxBytes=10*1024*1024,
            backupCount=5
        )
    ]
)
logger = logging.getLogger(__name__)


async def setup_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher()
    
    dp.message.middleware(AuthMiddleware(bot))
    dp.callback_query.middleware(AuthMiddleware(bot))
    
    dp.include_router(start_router)
    dp.include_router(savemode_router)
    dp.include_router(business_router)
    
    return dp


async def main():
    logger.info("🚀 Запуск SafeSaverX...")
    logger.info(f"📌 Режим: {settings.TELEGRAM_MODE}")
    
    try:
        await init_db()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return
    
    if settings.OWNER_TELEGRAM_ID:
        try:
            owner = await UserRepository.get_or_create(settings.OWNER_TELEGRAM_ID)
            if owner:
                await UserRepository.update_settings(settings.OWNER_TELEGRAM_ID, is_admin=True)
                logger.info(f"👤 Владелец бота: {settings.OWNER_TELEGRAM_ID}")
        except Exception as e:
            logger.error(f"❌ Ошибка создания владельца: {e}")
    
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = await setup_dispatcher(bot)
    
    allowed_updates = list(Update.model_fields.keys())
    logger.info(f"📋 Поддерживаемые апдейты: {len(allowed_updates)} типов")
    
    asyncio.create_task(scheduled_cleanup())
    logger.info("✅ Планировщик задач запущен")
    
    logger.info("✅ Бот запущен и готов к работе!")
    
    try:
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    except Exception as e:
        logger.error(f"❌ Ошибка при работе бота: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")