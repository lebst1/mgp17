from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from src.config import settings  # ✅ ИСПРАВЛЕНО: импортируем settings

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем движок
engine = create_async_engine(
    settings.DATABASE_URL,  # ✅ ИСПРАВЛЕНО: используем settings
    echo=False,
    future=True
)

# Создаем фабрику сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получить асинхронную сессию (для совместимости)"""
    async with async_session() as session:
        return session