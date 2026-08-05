import logging
from aiogram import Bot
from src.config import settings

logger = logging.getLogger(__name__)


async def notify_admin(message: str, error: Exception = None):
    """Отправляет уведомление админу об ошибке"""
    if not settings.OWNER_TELEGRAM_ID:
        return
    
    try:
        bot = Bot(token=settings.BOT_TOKEN)
        
        text = f"⚠️ <b>Ошибка в SafeSaverX!</b>\n\n{message}"
        if error:
            text += f"\n\n❌ <b>Ошибка:</b>\n<code>{str(error)}</code>"
        
        await bot.send_message(
            chat_id=settings.OWNER_TELEGRAM_ID,
            text=text,
            parse_mode="HTML"
        )
        await bot.session.close()
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление: {e}")