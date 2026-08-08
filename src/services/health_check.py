import logging
from datetime import datetime
from aiogram import Bot

from src.config import settings
from src.db.session import async_session
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def check_health(bot: Bot) -> dict:
    """Проверяет состояние бота"""
    result = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }
    
    # Проверка БД
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        result["checks"]["database"] = "ok"
    except Exception as e:
        result["checks"]["database"] = f"error: {str(e)[:50]}"
        result["status"] = "degraded"
    
    # Проверка бота
    try:
        me = await bot.get_me()
        result["checks"]["bot"] = f"ok ({me.username})"
    except Exception as e:
        result["checks"]["bot"] = f"error: {str(e)[:50]}"
        result["status"] = "degraded"
    
    return result