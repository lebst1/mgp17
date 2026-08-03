import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.db.session import init_db
from src.db.repositories.user_repository import UserRepository
from src.bot.middlewares.auth import AuthMiddleware, AdminMiddleware
from src.bot.handlers import start, savemode

# Импорты для AI и dot команд (если они есть)
# from src.bot.handlers import ai, dot_commands, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def setup_dispatcher() -> Dispatcher:
    """Настройка диспетчера"""
    dp = Dispatcher()
    
    # Подключаем middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    # Подключаем роутеры
    dp.include_router(start.router)
    dp.include_router(savemode.router)
    
    # Подключаем другие роутеры (раскомментировать когда появятся)
    # dp.include_router(ai.router)
    # dp.include_router(dot_commands.router)
    # dp.include_router(admin.router)
    
    return dp


async def main():
    """Главная функция запуска"""
    logger.info("🚀 Запуск Mnemora...")
    
    # Инициализация БД
    await init_db()
    logger.info("✅ База данных инициализирована")
    
    # Создаем владельца в БД
    if settings.OWNER_TELEGRAM_ID:
        owner = await UserRepository.get_or_create(settings.OWNER_TELEGRAM_ID)
        if owner:
            await UserRepository.update_settings(
                settings.OWNER_TELEGRAM_ID,
                is_admin=True
            )
            logger.info(f"👤 Владелец бота: {settings.OWNER_TELEGRAM_ID}")
    
    # Настраиваем бота
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Настраиваем диспетчер
    dp = await setup_dispatcher()
    
    # Запускаем поллинг
    logger.info("✅ Бот запущен и готов к работе!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")