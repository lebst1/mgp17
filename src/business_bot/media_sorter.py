import os
import logging
from datetime import datetime
from aiogram import Bot
from aiogram.types import FSInputFile
from src.config import settings
from src.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

PHOTO_CHAT_ID = -5115450517      # Чат для фото
VIDEO_CHAT_ID = -5108934738      # Чат для видео
VOICE_CHAT_ID = -5485070083      # Чат для голосовых и кружков
DOCUMENT_CHAT_ID = -5417507572   # Чат для документов


async def sort_and_send_media(bot: Bot, user_id: int, saved_msg):
    """Сортирует медиа по чатам и отправляет ВЛАДЕЛЬЦУ"""
    
    if not saved_msg.media_path or not os.path.exists(saved_msg.media_path):
        return
    
    # Определяем, в какой чат отправить
    chat_id = None
    media_type = saved_msg.media_type
    
    if media_type in ["photo"]:
        chat_id = PHOTO_CHAT_ID
    elif media_type in ["video", "animation"]:
        chat_id = VIDEO_CHAT_ID
    elif media_type in ["voice", "video_note"]:
        chat_id = VOICE_CHAT_ID
    elif media_type in ["document", "audio"]:
        chat_id = DOCUMENT_CHAT_ID
    else:
        # Если тип неизвестен — отправляем в документы
        chat_id = DOCUMENT_CHAT_ID
    
    if not chat_id:
        return
    
    # 📝 Формируем подпись
    from_user = saved_msg.from_username or saved_msg.from_first_name or "Неизвестно"
    chat_title = saved_msg.chat_title or "Личный чат"
    date_str = saved_msg.saved_at.strftime("%d.%m.%Y %H:%M") if saved_msg.saved_at else ""
    
    # ID пользователя, от которого медиа
    from_user_id = saved_msg.from_user_id or "Неизвестно"
    
    caption = f"""
📎 <b>От:</b> {from_user}
🆔 <code>{from_user_id}</code>
💬 <b>Чат:</b> {chat_title}
🕐 <b>Дата:</b> {date_str}
"""
    
    if saved_msg.text:
        caption += f"\n📝 <b>Текст:</b>\n<blockquote>{saved_msg.text[:200]}</blockquote>"
    
    # 🚀 Отправляем медиа
    try:
        media_file = FSInputFile(saved_msg.media_path)
        
        if media_type == "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=media_file,
                caption=caption,
                parse_mode="HTML"
            )
        elif media_type in ["video", "animation"]:
            await bot.send_video(
                chat_id=chat_id,
                video=media_file,
                caption=caption,
                parse_mode="HTML"
            )
        elif media_type == "video_note":
            await bot.send_video_note(chat_id=chat_id, video_note=media_file)
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
        elif media_type in ["voice", "audio"]:
            await bot.send_voice(
                chat_id=chat_id,
                voice=media_file,
                caption=caption,
                parse_mode="HTML"
            )
        elif media_type == "sticker":
            await bot.send_sticker(chat_id=chat_id, sticker=media_file)
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
        else:
            await bot.send_document(
                chat_id=chat_id,
                document=media_file,
                caption=caption,
                parse_mode="HTML"
            )
            
        logger.info(f"✅ Медиа отправлено владельцу в чат {chat_id} (от {from_user_id})")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки медиа: {e}")