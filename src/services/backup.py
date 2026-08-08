import os
import shutil
import logging
from datetime import datetime
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)


async def create_backup():
    """Создает бэкап базы данных"""
    try:
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        if not os.path.exists(db_path):
            logger.error(f"❌ Файл БД не найден: {db_path}")
            return None
        
        # Создаем папку для бэкапов
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        # Имя бэкапа с датой
        date = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{backup_dir}/app_{date}.db"
        
        # Копируем файл
        shutil.copy2(db_path, backup_path)
        
        # Удаляем старые бэкапы (оставляем только последние 7)
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("app_") and f.endswith(".db")])
        if len(backups) > 7:
            for old_backup in backups[:-7]:
                os.remove(os.path.join(backup_dir, old_backup))
                logger.info(f"🗑️ Удален старый бэкап: {old_backup}")
        
        logger.info(f"✅ Бэкап создан: {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания бэкапа: {e}")
        return None


async def backup_loop():
    """Фоновый цикл создания бэкапов (раз в день)"""
    import asyncio
    logger.info("🔄 Запущен фоновый сервис бэкапов (раз в день)")
    
    while True:
        try:
            await create_backup()
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле бэкапов: {e}")
        
        # Ждем 24 часа
        await asyncio.sleep(86400)