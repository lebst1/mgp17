import logging
import traceback
from datetime import datetime
from aiogram import Bot

from src.config import settings

logger = logging.getLogger(__name__)


async def send_error_to_telegram(error: Exception, context: str = "", bot: Bot = None):
    """Отправляет ошибку владельцу в Telegram"""
    try:
        if not bot:
            return
        
        error_text = f"""
⚠️ <b>Ошибка в боте!</b>

📌 <b>Контекст:</b> {context}
🕐 <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

<b>Текст ошибки:</b>
<code>{str(error)[:300]}</code>

<b>Traceback:</b>
<code>{traceback.format_exc()[-500:]}</code>
"""
        
        await bot.send_message(
            chat_id=settings.OWNER_TELEGRAM_ID,
            text=error_text,
            parse_mode="HTML"
        )
        logger.info(f"✅ Уведомление об ошибке отправлено владельцу")
        
    except Exception as e:
        logger.error(f"❌ Не удалось отправить уведомление об ошибке: {e}")