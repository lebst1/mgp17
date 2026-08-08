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


async def cleanup_media_if_needed():
    """Очищает медиа, если папка превышает лимит"""
    try:
        media_dir = settings.MEDIA_DIR
        if not os.path.exists(media_dir):
            return
        
        # Лимит — 500 МБ
        MAX_MEDIA_SIZE_MB = 500
        max_bytes = MAX_MEDIA_SIZE_MB * 1024 * 1024
        
        # Считаем размер папки
        total_size = 0
        files = []
        for f in os.listdir(media_dir):
            f_path = os.path.join(media_dir, f)
            if os.path.isfile(f_path):
                size = os.path.getsize(f_path)
                total_size += size
                files.append((f_path, size))
        
        # Если меньше лимита — ничего не делаем
        if total_size < max_bytes:
            logger.info(f"💾 Медиа: {total_size/1024/1024:.2f} МБ (лимит {MAX_MEDIA_SIZE_MB} МБ) — очистка не нужна")
            return
        
        # Сортируем по дате создания (старые сначала)
        files.sort(key=lambda x: os.path.getctime(x[0]))
        
        # Удаляем старые файлы, пока не освободим место
        freed = 0
        removed = 0
        for f_path, size in files:
            if total_size - freed < max_bytes:
                break
            try:
                os.remove(f_path)
                freed += size
                removed += 1
            except Exception as e:
                logger.error(f"❌ Не удалось удалить {f_path}: {e}")
        
        logger.info(f"🗑️ Очистка медиа: удалено {removed} файлов ({freed/1024/1024:.2f} МБ)")
        logger.info(f"💾 Текущий размер: {(total_size - freed)/1024/1024:.2f} МБ")
        
    except Exception as e:
        logger.error(f"❌ Ошибка очистки медиа: {e}")


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