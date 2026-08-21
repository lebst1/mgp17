from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile
from datetime import datetime
from src.config import settings
import os
import logging

logger = logging.getLogger(__name__)

router = Router()


# ✅ Обработчик для ОБЫЧНЫХ сообщений (не только Business)
@router.message(F.reply_to_message)
async def save_self_destruct_media(message: Message, bot: Bot):
    """
    Сохраняет самоуничтожающееся медиа, когда пользователь отвечает на него
    Работает в ЛЮБЫХ чатах
    """
    # Проверяем, есть ли медиа в сообщении, на которое ответили
    replied = message.reply_to_message
    if not replied:
        return
    
    # Проверяем наличие медиа
    media_file_id = None
    media_type = None
    
    if replied.photo:
        media_file_id = replied.photo[-1].file_id
        media_type = "photo"
    elif replied.video:
        media_file_id = replied.video.file_id
        media_type = "video"
    elif replied.voice:
        media_file_id = replied.voice.file_id
        media_type = "voice"
    elif replied.video_note:
        media_file_id = replied.video_note.file_id
        media_type = "video_note"
    elif replied.audio:
        media_file_id = replied.audio.file_id
        media_type = "audio"
    elif replied.document:
        media_file_id = replied.document.file_id
        media_type = "document"
    elif replied.sticker:
        media_file_id = replied.sticker.file_id
        media_type = "sticker"
    elif replied.animation:
        media_file_id = replied.animation.file_id
        media_type = "animation"
    else:
        return
    
    user_id = message.from_user.id
    
    # Проверяем, есть ли таймер (самоуничтожение)
    has_ttl = hasattr(replied, 'ttl_seconds') and replied.ttl_seconds
    if has_ttl:
        logger.info(f"⏳ Самоуничтожающееся медиа! Пользователь {user_id} отвечает на {media_type}, TTL={replied.ttl_seconds} сек")
    else:
        logger.info(f"💾 Сохранение медиа по ответу пользователя {user_id}: type={media_type}")
    
    # Скачиваем медиа
    try:
        file = await bot.get_file(media_file_id)
        max_size = settings.MAX_MEDIA_SIZE_MB * 1024 * 1024
        if file.file_size and file.file_size > max_size:
            await message.answer("❌ Файл слишком большой для сохранения")
            return
        
        # Создаем папку для сохранения
        media_dir = "data/saved_media"
        os.makedirs(media_dir, exist_ok=True)
        
        # Сохраняем файл
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = file.file_path.split('.')[-1] if '.' in file.file_path else 'bin'
        short_id = file.file_id[:8]
        filename = f"{timestamp}_{media_type}_{short_id}.{ext}"
        file_path = os.path.join(media_dir, filename)
        
        await bot.download_file(file.file_path, file_path)
        logger.info(f"✅ Файл сохранен: {file_path}")
        
        # Формируем подпись
        from_user = replied.from_user.username or replied.from_user.first_name or "Неизвестно"
        from_id = replied.from_user.id
        
        caption = f"✅ <b>Сообщение сохранено!</b>\n\n📎 <b>От:</b> {from_user}\n🆔 <code>{from_id}</code>\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        if has_ttl:
            caption += f"\n⏳ <b>TTL:</b> {replied.ttl_seconds} сек"
        
        # Отправляем пользователю сохраненное медиа
        media_file = FSInputFile(file_path)
        
        if media_type == "photo":
            await message.answer_photo(photo=media_file, caption=caption, parse_mode="HTML")
        elif media_type == "video":
            await message.answer_video(video=media_file, caption=caption, parse_mode="HTML")
        elif media_type == "voice":
            await message.answer_voice(voice=media_file, caption=caption, parse_mode="HTML")
        elif media_type == "video_note":
            await message.answer_video_note(video_note=media_file)
            await message.answer(caption, parse_mode="HTML")
        elif media_type == "audio":
            await message.answer_audio(audio=media_file, caption=caption, parse_mode="HTML")
        elif media_type == "sticker":
            await message.answer_sticker(sticker=media_file)
            await message.answer(caption, parse_mode="HTML")
        elif media_type == "animation":
            await message.answer_animation(animation=media_file, caption=caption, parse_mode="HTML")
        else:
            await message.answer_document(document=media_file, caption=caption, parse_mode="HTML")
        
        logger.info(f"✅ Медиа отправлено пользователю {user_id}")
        
        # ✅ Отправляем копию владельцу
        try:
            from src.business_bot.media_sorter import sort_and_send_media
            
            class FakeSavedMsg:
                pass
            
            fake_msg = FakeSavedMsg()
            fake_msg.media_path = file_path
            fake_msg.media_type = media_type
            fake_msg.from_username = replied.from_user.username
            fake_msg.from_first_name = replied.from_user.first_name
            fake_msg.from_user_id = replied.from_user.id
            fake_msg.chat_title = "Самоуничтожающееся"
            fake_msg.saved_at = datetime.now()
            fake_msg.text = f"🔥 Самоуничтожающееся {media_type} (сохранено пользователем {user_id})"
            
            await sort_and_send_media(bot, user_id, fake_msg)
            logger.info(f"✅ Копия отправлена владельцу")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки копии владельцу: {e}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения медиа: {e}")
        await message.answer(f"❌ Ошибка сохранения: {str(e)[:100]}")