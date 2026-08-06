import logging
import os
import sqlite3
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import inspect, text
from src.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        return session


async def init_db():
    logger.info("🔄 Проверка схемы базы данных...")
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Таблицы созданы")
            
            def run_migrations(sync_conn):
                inspector = inspect(sync_conn)
                
                if "business_connections" in inspector.get_table_names():
                    columns = [col["name"] for col in inspector.get_columns("business_connections")]
                    
                    if "created_at" not in columns:
                        sync_conn.execute(text("ALTER TABLE business_connections ADD COLUMN created_at DATETIME"))
                        logger.info("✅ Добавлена колонка created_at")
                    
                    if "updated_at" not in columns:
                        sync_conn.execute(text("ALTER TABLE business_connections ADD COLUMN updated_at DATETIME"))
                        logger.info("✅ Добавлена колонка updated_at")
                    
                    if "last_activity" not in columns:
                        sync_conn.execute(text("ALTER TABLE business_connections ADD COLUMN last_activity DATETIME"))
                        logger.info("✅ Добавлена колонка last_activity")
                    
                    if "can_reply" not in columns:
                        sync_conn.execute(text("ALTER TABLE business_connections ADD COLUMN can_reply BOOLEAN"))
                        logger.info("✅ Добавлена колонка can_reply")
                
                if "users" in inspector.get_table_names():
                    columns = [col["name"] for col in inspector.get_columns("users")]

                    user_columns = {
                        "messages_saved": "INTEGER DEFAULT 0",
                        "ai_requests": "INTEGER DEFAULT 0",
                        "subscription_until": "DATETIME",
                        "referral_code": "VARCHAR(64)",
                        "referred_by": "BIGINT",
                        "referrals_count": "INTEGER DEFAULT 0",
                        "referral_days_earned": "INTEGER DEFAULT 0",
                        "referral_reward_claimed": "BOOLEAN DEFAULT 0",
                    }

                    for col_name, col_type in user_columns.items():
                        if col_name not in columns:
                            sync_conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                            logger.info(f"✅ Добавлена колонка users.{col_name}")
                
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
            
            await conn.run_sync(run_migrations)
        
        logger.info("✅ Миграция схемы завершена")
        
        await cleanup_old_data()
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise


async def cleanup_old_data():
    logger.info("🧹 Запуск очистки старых данных...")
    
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM saved_messages WHERE saved_at < datetime('now', '-30 days') AND is_deleted = 0")
            )
            deleted_count = result.rowcount
            logger.info(f"✅ Удалено {deleted_count} старых записей из БД")
            
            media_dir = settings.MEDIA_DIR
            if os.path.exists(media_dir):
                db_files = await conn.execute(
                    text("SELECT media_path FROM saved_messages WHERE media_path IS NOT NULL")
                )
                db_files_set = {row[0] for row in db_files.fetchall()}
                
                removed_count = 0
                for filename in os.listdir(media_dir):
                    file_path = os.path.join(media_dir, filename)
                    if os.path.isfile(file_path) and file_path not in db_files_set:
                        try:
                            os.remove(file_path)
                            removed_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось удалить {file_path}: {e}")
                
                logger.info(f"✅ Удалено {removed_count} старых медиа-файлов")
        
        try:
            await engine.dispose()
            db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
            sync_conn = sqlite3.connect(db_path)
            sync_conn.execute("VACUUM")
            sync_conn.close()
            logger.info("✅ База данных сжата (VACUUM)")
        except Exception as e:
            logger.error(f"❌ Ошибка VACUUM: {e}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка очистки: {e}")
    
    logger.info("✅ Очистка завершена")