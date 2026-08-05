import asyncio
import logging
import os
import shutil
from datetime import datetime
from src.db.session import cleanup_old_data
from src.config import settings

logger = logging.getLogger(__name__)


async def scheduled_cleanup():
    """Запускает очистку по расписанию"""
    while True:
        try:
            # Ждём до 3:00 ночи
            now = datetime.now()
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target.replace(day=now.day + 1)
            
            wait_seconds = (target - now).total_seconds()
            logger.info(f"⏳ Очистка запустится через {wait_seconds/3600:.1f} часов")
            await asyncio.sleep(wait_seconds)
            
            # Запускаем очистку
            logger.info("🧹 Запуск плановой очистки...")
            await cleanup_old_data()
            
            # Создаём бэкап раз в неделю
            if datetime.now().weekday() == 0:  # Понедельник
                await create_backup()
                
        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике: {e}")
            await asyncio.sleep(3600)  # Ждём час и пробуем снова


async def create_backup():
    """Создаёт бэкап БД и медиа"""
    try:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        date = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Бэкап БД
        if os.path.exists("data/app.db"):
            shutil.copy2("data/app.db", f"{backup_dir}/app_{date}.db")
            logger.info(f"✅ Бэкап БД: app_{date}.db")
        
        # Удаляем бэкапы старше 7 дней
        for f in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, f)
            if os.path.isfile(file_path):
                # Если файл старше 7 дней
                if os.path.getmtime(file_path) < (datetime.now().timestamp() - 7 * 86400):
                    os.remove(file_path)
                    logger.info(f"🗑️ Удалён старый бэкап: {f}")
                    
    except Exception as e:
        logger.error(f"❌ Ошибка бэкапа: {e}")