import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import inspect, text
from src.config import settings

logger = logging.getLogger(__name__)

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем движок
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

# Создаем фабрику сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """Получить асинхронную сессию"""
    async with async_session() as session:
        return session


async def init_db():
    """Инициализация и миграция базы данных"""
    logger.info("🔄 Проверка схемы базы данных...")
    
    async with engine.begin() as conn:
        # Создаем таблицы, которых еще нет
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Таблицы созданы")
        
        # Выполняем миграции через синхронную функцию
        def run_migrations(sync_conn):
            """Синхронная функция для миграций"""
            inspector = inspect(sync_conn)
            
            # Проверяем таблицу business_connections
            if "business_connections" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("business_connections")]
                
                # ✅ ИСПРАВЛЕНО: Проверяем правильные имена колонок
                if "created_at" not in columns:
                    sync_conn.execute(text("ALTER TABLE business_connections ADD COLUMN created_at DATETIME"))
                    logger.info("✅ Добавлена колонка created_at")
                
                if "last_activity" not in columns:
                    sync_conn.execute(text("ALTER TABLE business_connections ADD COLUMN last_activity DATETIME"))
                    logger.info("✅ Добавлена колонка last_activity")
                
                if "can_reply" not in columns:
                    sync_conn.execute(text("ALTER TABLE business_connections ADD COLUMN can_reply BOOLEAN"))
                    logger.info("✅ Добавлена колонка can_reply")
            
            # Проверяем таблицу users
            if "users" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("users")]
                
                if "messages_saved" not in columns:
                    sync_conn.execute(text("ALTER TABLE users ADD COLUMN messages_saved INTEGER DEFAULT 0"))
                    logger.info("✅ Добавлена колонка messages_saved")
                
                if "ai_requests" not in columns:
                    sync_conn.execute(text("ALTER TABLE users ADD COLUMN ai_requests INTEGER DEFAULT 0"))
                    logger.info("✅ Добавлена колонка ai_requests")
            
            # Проверяем таблицу saved_messages
            if "saved_messages" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("saved_messages")]
                
                columns_to_add = {
                    "connection_id": "VARCHAR(255)",
                    "chat_title": "VARCHAR(255)",
                    "from_user_id": "BIGINT",
                    "from_username": "VARCHAR(255)",
                    "from_first_name": "VARCHAR(255)",
                    "media_type": "VARCHAR(50)",
                    "media_file_id": "VARCHAR(255)",
                    "media_path": "VARCHAR(500)",
                    "media_size": "INTEGER",
                    "is_deleted": "BOOLEAN DEFAULT 0",
                    "is_edited": "BOOLEAN DEFAULT 0",
                    "edit_history": "TEXT",
                    "original_date": "DATETIME"
                }
                
                for col_name, col_type in columns_to_add.items():
                    if col_name not in columns:
                        try:
                            sync_conn.execute(text(f"ALTER TABLE saved_messages ADD COLUMN {col_name} {col_type}"))
                            logger.info(f"✅ Добавлена колонка: {col_name}")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось добавить {col_name}: {e}")
        
        # Запускаем миграции
        await conn.run_sync(run_migrations)
    
    logger.info("✅ Миграция схемы завершена")