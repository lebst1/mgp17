import logging
import json
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, BusinessConnection, BusinessMessagesDeleted, FSInputFile
from aiogram.filters import Command
from datetime import datetime
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository
from src.db.repositories.business_repository import BusinessRepository
from src.db.session import async_session
from src.config import settings

logger = logging.getLogger(__name__)

router = Router()
MEDIA_DIR = settings.MEDIA_DIR
MAX_FILE_SIZE = settings.MAX_MEDIA_SIZE_MB * 1024 * 1024


async def download_media(bot: Bot, file_id: str) -> str:
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        file = await bot.get_file(file_id)
        if file.file_size and file.file_size > MAX_FILE_SIZE:
            logger.warning(f"⚠️ Файл слишком большой ({file.file_size} байт), пропускаем")
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = file.file_path.split('.')[-1] if '.' in file.file_path else 'bin'
        filename = f"{timestamp}_{file_id[:8]}.{ext}"
        file_path = os.path.join(MEDIA_DIR, filename)
        await bot.download_file(file.file_path, file_path)
        logger.info(f"✅ Медиа сохранено: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания медиа: {e}")
        return None


async def send_deleted_notification(bot: Bot, user_id: int, saved_msg):
    username = saved_msg.from_username or saved_msg.from_first_name or "пользователь"
    
    text = f"""
🗑️ <b>{username}</b> удалил сообщение.

<blockquote>{saved_msg.text or 'Медиафайл'}</blockquote>

💬 {saved_msg.chat_title or 'Личный чат'}
"""
    
    media_path = saved_msg.media_path
    if media_path and os.path.exists(media_path):
        try:
            media_file = FSInputFile(media_path)
            
            if saved_msg.media_type == "photo":
                await bot.send_photo(chat_id=user_id, photo=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "video":
                await bot.send_video(chat_id=user_id, video=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "video_note":
                await bot.send_video_note(chat_id=user_id, video_note=media_file)
                await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
            elif saved_msg.media_type == "document":
                await bot.send_document(chat_id=user_id, document=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "audio":
                await bot.send_audio(chat_id=user_id, audio=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "voice":
                await bot.send_voice(chat_id=user_id, voice=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "sticker":
                await bot.send_sticker(chat_id=user_id, sticker=media_file)
                await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
            else:
                await bot.send_document(chat_id=user_id, document=media_file, caption=text, parse_mode="HTML")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки медиа: {e}")
    
    await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")


async def send_edit_notification(bot: Bot, user_id: int, saved_msg, old_text: str, new_text: str):
    username = saved_msg.from_username or saved_msg.from_first_name or "пользователь"
    
    text = f"""
✏️ <b>{username}</b> отредактировал сообщение.

<blockquote>{old_text or 'Без текста'}</blockquote>

↓↓↓

<blockquote>{new_text or 'Без текста'}</blockquote>

💬 {saved_msg.chat_title or 'Личный чат'}
"""
    
    media_path = saved_msg.media_path
    if media_path and os.path.exists(media_path):
        try:
            media_file = FSInputFile(media_path)
            
            if saved_msg.media_type == "photo":
                await bot.send_photo(chat_id=user_id, photo=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "video":
                await bot.send_video(chat_id=user_id, video=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "video_note":
                await bot.send_video_note(chat_id=user_id, video_note=media_file)
                await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
            elif saved_msg.media_type == "document":
                await bot.send_document(chat_id=user_id, document=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "audio":
                await bot.send_audio(chat_id=user_id, audio=media_file, caption=text, parse_mode="HTML")
            elif saved_msg.media_type == "voice":
                await bot.send_voice(chat_id=user_id, voice=media_file, caption=text, parse_mode="HTML")
            else:
                await bot.send_document(chat_id=user_id, document=media_file, caption=text, parse_mode="HTML")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки медиа с правкой: {e}")
    
    await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")


def extract_media_from_message(message: Message):
    """Универсальное извлечение медиа из сообщения (включая view-once/self-destruct)"""
    media_file_id = None
    media_type = None
    media_size = None
    
    # ✅ 1. Сначала проверяем стандартные поля (для обычных сообщений)
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
        media_size = message.photo[-1].file_size
        logger.info(f"📸 Найден file_id через message.photo: {media_file_id}")
        return media_file_id, media_type, media_size
    
    if message.video:
        media_file_id = message.video.file_id
        media_type = "video"
        media_size = message.video.file_size
        logger.info(f"📸 Найден file_id через message.video: {media_file_id}")
        return media_file_id, media_type, media_size
    
    if message.voice:
        media_file_id = message.voice.file_id
        media_type = "voice"
        media_size = message.voice.file_size
        logger.info(f"📸 Найден file_id через message.voice: {media_file_id}")
        return media_file_id, media_type, media_size
    
    if message.video_note:
        media_file_id = message.video_note.file_id
        media_type = "video_note"
        media_size = message.video_note.file_size
        logger.info(f"📸 Найден file_id через message.video_note: {media_file_id}")
        return media_file_id, media_type, media_size
    
    if message.document:
        media_file_id = message.document.file_id
        media_type = "document"
        media_size = message.document.file_size
        logger.info(f"📸 Найден file_id через message.document: {media_file_id}")
        return media_file_id, media_type, media_size
    
    if message.audio:
        media_file_id = message.audio.file_id
        media_type = "audio"
        media_size = message.audio.file_size
        logger.info(f"📸 Найден file_id через message.audio: {media_file_id}")
        return media_file_id, media_type, media_size
    
    if message.sticker:
        media_file_id = message.sticker.file_id
        media_type = "sticker"
        media_size = message.sticker.file_size
        logger.info(f"📸 Найден file_id через message.sticker: {media_file_id}")
        return media_file_id, media_type, media_size
    
    if message.animation:
        media_file_id = message.animation.file_id
        media_type = "animation"
        media_size = message.animation.file_size
        logger.info(f"📸 Найден file_id через message.animation: {media_file_id}")
        return media_file_id, media_type, media_size
    
    # ✅ 2. Если не нашли — проверяем message.media (для self-destruct/view-once)
    if hasattr(message, 'media') and message.media:
        logger.info(f"🔄 Проверяем message.media: {type(message.media)}")
        
        media_obj = message.media
        
        # Пробуем получить file_id из разных типов media
        if hasattr(media_obj, 'photo') and media_obj.photo:
            if isinstance(media_obj.photo, list):
                media_file_id = media_obj.photo[-1].file_id
            else:
                media_file_id = media_obj.photo.file_id
            media_type = "photo"
            logger.info(f"✅ Найден file_id через media.photo: {media_file_id}")
            return media_file_id, media_type, media_size
        
        if hasattr(media_obj, 'video') and media_obj.video:
            media_file_id = media_obj.video.file_id
            media_type = "video"
            media_size = media_obj.video.file_size
            logger.info(f"✅ Найден file_id через media.video: {media_file_id}")
            return media_file_id, media_type, media_size
        
        if hasattr(media_obj, 'document') and media_obj.document:
            media_file_id = media_obj.document.file_id
            media_type = "document"
            media_size = media_obj.document.file_size
            logger.info(f"✅ Найден file_id через media.document: {media_file_id}")
            return media_file_id, media_type, media_size
        
        if hasattr(media_obj, 'voice') and media_obj.voice:
            media_file_id = media_obj.voice.file_id
            media_type = "voice"
            media_size = media_obj.voice.file_size
            logger.info(f"✅ Найден file_id через media.voice: {media_file_id}")
            return media_file_id, media_type, media_size
        
        if hasattr(media_obj, 'video_note') and media_obj.video_note:
            media_file_id = media_obj.video_note.file_id
            media_type = "video_note"
            media_size = media_obj.video_note.file_size
            logger.info(f"✅ Найден file_id через media.video_note: {media_file_id}")
            return media_file_id, media_type, media_size
        
        if hasattr(media_obj, 'audio') and media_obj.audio:
            media_file_id = media_obj.audio.file_id
            media_type = "audio"
            media_size = media_obj.audio.file_size
            logger.info(f"✅ Найден file_id через media.audio: {media_file_id}")
            return media_file_id, media_type, media_size
        
        if hasattr(media_obj, 'sticker') and media_obj.sticker:
            media_file_id = media_obj.sticker.file_id
            media_type = "sticker"
            media_size = media_obj.sticker.file_size
            logger.info(f"✅ Найден file_id через media.sticker: {media_file_id}")
            return media_file_id, media_type, media_size
        
        if hasattr(media_obj, 'animation') and media_obj.animation:
            media_file_id = media_obj.animation.file_id
            media_type = "animation"
            media_size = media_obj.animation.file_size
            logger.info(f"✅ Найден file_id через media.animation: {media_file_id}")
            return media_file_id, media_type, media_size
        
        # Если есть прямой file_id
        if hasattr(media_obj, 'file_id') and media_obj.file_id:
            media_file_id = media_obj.file_id
            media_type = "media"
            logger.info(f"✅ Найден file_id через media.file_id: {media_file_id}")
            return media_file_id, media_type, media_size
    
    return None, None, None


@router.business_connection()
async def handle_business_connection(event: BusinessConnection, bot: Bot):
    user_id = event.user.id
    connection_id = event.id
    
    logger.info(f"🔗 Business подключение: {connection_id}")
    logger.info(f"👤 Пользователь: {user_id}")
    logger.info(f"📊 Статус: {event.is_enabled}")
    
    user, _ = await UserRepository.get_or_create(
        telegram_id=user_id,
        username=event.user.username,
        first_name=event.user.first_name,
        last_name=event.user.last_name
    )
    
    await BusinessRepository.save_connection(
        connection_id=connection_id,
        user_telegram_id=user_id,
        is_enabled=event.is_enabled
    )
    
    await bot.send_message(
        chat_id=user_id,
        text="✅ Ваш бизнес-аккаунт подключен к SafeSaverX!\n\n"
             "Теперь я буду сохранять удаленные и отредактированные сообщения.\n"
             "Чтобы проверить статус, отправьте /business_status"
    )
    logger.info(f"✅ Отправлено приветствие пользователю {user_id}")


@router.business_message()
async def handle_business_message(message: Message):
    if message.edit_date is not None:
        return
    
    if not message.from_user:
        return
    
    connection_id = message.business_connection_id
    if not connection_id:
        return
    
    logger.info(f"📩 Новое сообщение с connection_id: {connection_id}")
    
    # ✅ ЛОГИРУЕМ СЫРОЕ СООБЩЕНИЕ для отладки (один раз)
    try:
        raw_json = json.dumps(message.model_dump(), default=str, ensure_ascii=False)
        # Логируем только если есть медиа или ttl
        if hasattr(message, 'media') and message.media or hasattr(message, 'ttl_seconds') and message.ttl_seconds:
            logger.info(f"🔍 Сырое сообщение: {raw_json[:500]}...")  # Обрезаем, чтобы не засорять логи
    except Exception as e:
        logger.error(f"❌ Ошибка логирования сырого сообщения: {e}")
    
    user = await BusinessRepository.get_user_by_connection(connection_id)
    if not user:
        logger.warning(f"⚠️ Неизвестный connection_id: {connection_id}, создаем новый")
        await BusinessRepository.get_or_create_connection_by_user(
            connection_id=connection_id,
            user_id=message.from_user.id
        )
        user = await UserRepository.get_by_id(message.from_user.id)
        if not user:
            logger.warning(f"⚠️ Пользователь {message.from_user.id} не найден")
            return
    
    try:
        # ✅ Проверяем, есть ли таймер (самоуничтожение)
        is_self_destruct = hasattr(message, 'ttl_seconds') and message.ttl_seconds
        if is_self_destruct:
            logger.info(f"⏳ Обнаружено самоуничтожающееся сообщение! TTL: {message.ttl_seconds} сек")
        
        # ✅ УНИВЕРСАЛЬНОЕ ИЗВЛЕЧЕНИЕ МЕДИА
        media_file_id, media_type, media_size = extract_media_from_message(message)
        
        message_data = {
            "user_id": user.telegram_id,
            "connection_id": connection_id,
            "chat_id": message.chat.id,
            "chat_title": message.chat.title or "Личный чат",
            "message_id": message.message_id,
            "from_user_id": message.from_user.id,
            "from_username": message.from_user.username,
            "from_first_name": message.from_user.first_name,
            "saved_at": datetime.utcnow(),
            "original_date": datetime.utcnow()
        }
        
        if media_file_id:
            # Определяем текст сообщения
            if is_self_destruct:
                message_data["text"] = f"🔥 САМОУНИЧТОЖАЮЩЕЕСЯ {media_type.upper()} (TTL: {message.ttl_seconds} сек)"
                if message.caption:
                    message_data["text"] += f"\n📝 {message.caption}"
            else:
                message_data["text"] = message.caption or f"{media_type}"
            
            # Проверяем размер
            if media_size and media_size > MAX_FILE_SIZE:
                logger.warning(f"⚠️ Файл слишком большой ({media_size} байт), пропускаем")
                return
            
            # Скачиваем медиа
            media_path = await download_media(message.bot, media_file_id)
            
            if media_path:
                message_data["media_path"] = media_path
                message_data["media_file_id"] = media_file_id
                message_data["media_type"] = media_type
                message_data["media_size"] = media_size
                
                logger.info(f"✅ Медиа сохранено: {media_path}")
            else:
                logger.warning(f"⚠️ Не удалось скачать медиа: {media_file_id}")
                return
        else:
            # Обычное текстовое сообщение
            message_data["text"] = message.text or ""
            saved_msg = await MessageRepository.save_message(message_data)
            logger.info(f"💾 Сохранено текстовое сообщение от {user.telegram_id}")
            return
        
        # Сохраняем в БД
        saved_msg = await MessageRepository.save_message(message_data)
        logger.info(f"💾 Сохранено сообщение от {user.telegram_id} в чате {message.chat.id}")
        
        # Отправляем владельцу
        if media_file_id and media_path:
            from src.business_bot.media_sorter import sort_and_send_media
            await sort_and_send_media(message.bot, user.telegram_id, saved_msg)
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения сообщения: {e}")


@router.deleted_business_messages()
async def handle_business_deleted(event: BusinessMessagesDeleted, bot: Bot):
    logger.info(f"🔍 Получено удаление бизнес-сообщений!")
    logger.info(f"🔗 business_connection_id: {event.business_connection_id}")
    logger.info(f"📋 message_ids: {event.message_ids}")
    logger.info(f"📌 chat_id: {event.chat.id}")

    owner = await BusinessRepository.get_user_by_connection(event.business_connection_id)
    if not owner:
        logger.warning(f"⚠️ Пользователь не найден для connection_id: {event.business_connection_id}")
        return

    for message_id in event.message_ids:
        try:
            saved_msg = await MessageRepository.get_by_id_and_chat(
                message_id=message_id,
                chat_id=event.chat.id,
                user_id=owner.telegram_id
            )
            
            if saved_msg:
                saved_msg.is_deleted = True
                async with async_session() as session:
                    await session.merge(saved_msg)
                    await session.commit()
                logger.info(f"✅ Сообщение {message_id} отмечено как удаленное")

                if saved_msg.from_user_id != owner.telegram_id:
                    await send_deleted_notification(bot, owner.telegram_id, saved_msg)
                    logger.info(f"✅ Уведомление отправлено владельцу {owner.telegram_id}")
                else:
                    logger.info(f"ℹ️ Сообщение {message_id} удалено владельцем, уведомление не отправляем")
            else:
                logger.warning(f"⚠️ Сообщение {message_id} не найдено в БД")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки удаления: {e}")


@router.edited_business_message()
async def handle_business_edited(message: Message):
    if not message.from_user:
        return
    
    connection_id = message.business_connection_id
    if not connection_id:
        return
    
    user = await BusinessRepository.get_user_by_connection(connection_id)
    if not user:
        logger.warning(f"⚠️ Пользователь не найден для connection_id: {connection_id}")
        return
    
    logger.info(f"✏️ Отредактировано сообщение {message.message_id} от {user.telegram_id}")
    logger.info(f"📝 Новый текст: {message.text or message.caption}")
    
    try:
        saved_msg = await MessageRepository.get_by_id_and_chat(
            message_id=message.message_id,
            chat_id=message.chat.id,
            user_id=user.telegram_id
        )
        
        if saved_msg:
            old_text = saved_msg.text or ""
            new_text = message.text or message.caption or ""
            
            history = json.loads(saved_msg.edit_history) if saved_msg.edit_history else []
            history.append({
                "old_text": old_text,
                "new_text": new_text,
                "edited_at": datetime.utcnow().isoformat()
            })
            
            saved_msg.text = new_text
            saved_msg.is_edited = True
            saved_msg.edit_history = json.dumps(history[-10:])
            
            async with async_session() as session:
                await session.merge(saved_msg)
                await session.commit()
                
            logger.info(f"✅ Обновлена история правок для сообщения {message.message_id}")
            
            if saved_msg.from_user_id != user.telegram_id:
                await send_edit_notification(message.bot, user.telegram_id, saved_msg, old_text, new_text)
                logger.info(f"✅ Уведомление о правке отправлено владельцу {user.telegram_id}")
            else:
                logger.info(f"ℹ️ Сообщение {message.message_id} отредактировано владельцем")
        else:
            logger.warning(f"⚠️ Сообщение {message.message_id} не найдено в БД")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки правки: {e}")


@router.message(Command("business_status"))
async def business_status(message: Message):
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        user, _ = await UserRepository.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
    
    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    
    status_text = f"""
📊 <b>Статус Business подключения</b>

👤 Пользователь: {user.first_name or user.username or str(user.telegram_id)}
✅ Аккаунт: {'активен' if user.is_active else 'заблокирован'}
🔗 Подключений: {len(connections)}
📊 Сохранено сообщений: {user.messages_saved}
"""
    
    if connections:
        status_text += "\n<b>Активные подключения:</b>\n"
        for conn in connections:
            status_text += f"• {conn.connection_id[:20]}... {'✅ активен' if conn.is_enabled else '❌ отключен'}\n"
            if conn.created_at:
                status_text += f"  Подключен: {conn.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            else:
                status_text += "  Подключен: Неизвестно\n"
    
    await message.answer(status_text, parse_mode="HTML")