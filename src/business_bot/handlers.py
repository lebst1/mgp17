import logging
import json
from aiogram import Router, F, Bot
from aiogram.types import Message, BusinessConnection
from aiogram.filters import Command
from datetime import datetime
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository
from src.db.repositories.business_repository import BusinessRepository
from src.db.session import async_session
from src.config import settings

logger = logging.getLogger(__name__)

router = Router()


# ✅ ПОДКЛЮЧЕНИЕ БИЗНЕС-АККАУНТА
@router.business_connection()
async def handle_business_connection(event: BusinessConnection, bot: Bot):
    user_id = event.user.id
    connection_id = event.id
    
    logger.info(f"🔗 Business подключение: {connection_id}")
    logger.info(f"👤 Пользователь: {user_id}")
    logger.info(f"📊 Статус: {event.is_enabled}")
    
    user = await UserRepository.get_or_create(
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
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text="✅ Ваш бизнес-аккаунт подключен к Mnemora!\n\n"
                 "Теперь я буду сохранять удаленные и отредактированные сообщения.\n"
                 "Чтобы проверить статус, отправьте /business_status"
        )
        logger.info(f"✅ Отправлено приветствие пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки приветствия: {e}")
    
    logger.info(f"✅ Пользователь {user_id} подключил бизнес-аккаунт")


# ✅ НОВЫЕ СООБЩЕНИЯ
@router.business_message()
async def handle_business_message(message: Message):
    """Обработчик новых бизнес-сообщений"""
    if message.edit_date is not None:
        return
    
    if not message.from_user:
        return
    
    connection_id = message.business_connection_id
    if not connection_id:
        return
    
    logger.info(f"📩 Новое сообщение с connection_id: {connection_id}")
    
    # Пытаемся получить пользователя
    user = await BusinessRepository.get_user_by_connection(connection_id)
    
    # Если не нашли — создаем новый connection_id
    if not user:
        logger.warning(f"⚠️ Неизвестный connection_id: {connection_id}, создаем новый")
        connection = await BusinessRepository.get_or_create_connection_by_user(
            connection_id=connection_id,
            user_id=message.from_user.id
        )
        user = await UserRepository.get_by_id(message.from_user.id)
        if not user:
            logger.warning(f"⚠️ Пользователь {message.from_user.id} не найден")
            return
    
    if not user.savemode_enabled:
        return
    
    try:
        message_data = {
            "user_id": user.telegram_id,
            "connection_id": connection_id,
            "chat_id": message.chat.id,
            "chat_title": message.chat.title or "Личный чат",
            "message_id": message.message_id,
            "from_user_id": message.from_user.id,
            "from_username": message.from_user.username,
            "from_first_name": message.from_user.first_name,
            "text": message.text or message.caption,
            "saved_at": datetime.utcnow(),
            "original_date": datetime.utcnow()
        }
        
        if message.photo:
            message_data["media_type"] = "photo"
            message_data["media_file_id"] = message.photo[-1].file_id
        elif message.video:
            message_data["media_type"] = "video"
            message_data["media_file_id"] = message.video.file_id
        elif message.document:
            message_data["media_type"] = "document"
            message_data["media_file_id"] = message.document.file_id
        elif message.audio:
            message_data["media_type"] = "audio"
            message_data["media_file_id"] = message.audio.file_id
        elif message.voice:
            message_data["media_type"] = "voice"
            message_data["media_file_id"] = message.voice.file_id
        elif message.sticker:
            message_data["media_type"] = "sticker"
            message_data["media_file_id"] = message.sticker.file_id
        
        await MessageRepository.save_message(message_data)
        logger.info(f"💾 Сохранено сообщение от {user.telegram_id} в чате {message.chat.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения сообщения: {e}")


# ✅ УДАЛЕННЫЕ СООБЩЕНИЯ — С УВЕДОМЛЕНИЕМ ВСЕМ ПОЛЬЗОВАТЕЛЯМ
@router.message(F.business_connection_id.is_not(None))
async def handle_business_deleted(message: Message, bot: Bot):
    """Обработчик удаленных сообщений с отправкой уведомления владельцу"""
    # Проверяем, что это именно удаление (нет текста и нет медиа)
    if message.text or message.caption or message.photo or message.video or message.document:
        return
    
    connection_id = message.business_connection_id
    if not connection_id:
        return
    
    logger.info(f"🔍 Получено удаление с connection_id: {connection_id}")
    
    if not message.from_user:
        logger.warning("⚠️ Нет from_user в удаленном сообщении")
        return
    
    user_id = message.from_user.id
    user = await UserRepository.get_by_id(user_id)
    
    if not user:
        logger.warning(f"⚠️ Пользователь {user_id} не найден")
        return
    
    logger.info(f"🗑 Удалено сообщение {message.message_id} в чате {message.chat.id} от {user.telegram_id}")
    
    # ✅ ПОМЕЧАЕМ КАК УДАЛЕННОЕ В БД
    try:
        await MessageRepository.mark_as_deleted(
            message_id=message.message_id,
            chat_id=message.chat.id,
            user_id=user.telegram_id
        )
        logger.info(f"✅ Сообщение {message.message_id} отмечено как удаленное")
    except Exception as e:
        logger.error(f"❌ Ошибка обработки удаления: {e}")
    
    # ✅ ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ ВЛАДЕЛЬЦУ В ЛС
    try:
        # Получаем сохраненное сообщение из БД
        saved_msg = await MessageRepository.get_by_id(
            message_id=message.message_id,
            user_id=user.telegram_id
        )
        
        if saved_msg:
            # Формируем текст уведомления
            notification_text = f"🗑 <b>Удалено сообщение</b>\n\n"
            notification_text += f"📌 <b>Чат:</b> {saved_msg.chat_title or saved_msg.chat_id}\n"
            if saved_msg.from_username:
                notification_text += f"👤 <b>От:</b> @{saved_msg.from_username}\n"
            if saved_msg.text:
                notification_text += f"📝 <b>Текст:</b>\n{saved_msg.text}\n"
            if saved_msg.media_type:
                notification_text += f"🖼️ <b>Медиа:</b> {saved_msg.media_type}\n"
            notification_text += f"🕐 <b>Время:</b> {saved_msg.saved_at.strftime('%d.%m.%Y %H:%M:%S')}"
            
            # Отправляем в ЛС владельцу
            await bot.send_message(
                chat_id=user.telegram_id,
                text=notification_text,
                parse_mode="HTML"
            )
            logger.info(f"✅ Уведомление об удалении отправлено пользователю {user.telegram_id}")
        else:
            logger.warning(f"⚠️ Сообщение {message.message_id} не найдено в БД для отправки уведомления")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")


# ✅ ОТРЕДАКТИРОВАННЫЕ СООБЩЕНИЯ
@router.business_message()
async def handle_business_edited(message: Message):
    """Обработчик отредактированных сообщений"""
    if not message.edit_date:
        return
    
    if not message.from_user:
        return
    
    connection_id = message.business_connection_id
    if not connection_id:
        return
    
    user = await BusinessRepository.get_user_by_connection(connection_id)
    if not user:
        return
    
    logger.info(f"✏️ Отредактировано сообщение {message.message_id} от {user.telegram_id}")
    
    try:
        saved_msg = await MessageRepository.get_by_id(
            message_id=message.message_id,
            user_id=user.telegram_id
        )
        
        if saved_msg and saved_msg.text != message.text:
            history = json.loads(saved_msg.edit_history) if saved_msg.edit_history else []
            history.append({
                "old_text": saved_msg.text,
                "new_text": message.text,
                "edited_at": datetime.utcnow().isoformat()
            })
            
            async with async_session() as session:
                saved_msg.text = message.text
                saved_msg.is_edited = True
                saved_msg.edit_history = json.dumps(history[-10:])
                await session.commit()
                
            logger.info(f"✅ Обновлена история правок для сообщения {message.message_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки правки: {e}")


# ✅ КОМАНДА /business_status
@router.message(Command("business_status"))
async def business_status(message: Message):
    """Проверить статус бизнес-подключения"""
    user = await UserRepository.get_by_id(message.from_user.id)
    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    
    status_text = f"""
📊 <b>Статус Business подключения</b>

👤 Пользователь: {user.first_name or user.username}
✅ Аккаунт: {'активен' if user.is_active else 'заблокирован'}
📝 SAVE MODE: {'✅ Включен' if user.savemode_enabled else '❌ Выключен'}
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


# ✅ КОМАНДА /savemode
@router.message(Command("savemode"))
async def toggle_savemode(message: Message):
    """Включить/выключить SAVE MODE"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("ℹ️ Использование: /savemode on - включить, /savemode off - выключить")
        return
    
    action = args[1].lower()
    
    if action not in ["on", "off"]:
        await message.answer("❌ Используйте 'on' или 'off'")
        return
    
    enabled = action == "on"
    user = await UserRepository.update_settings(message.from_user.id, savemode_enabled=enabled)
    
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        return
    
    status = "включен" if enabled else "выключен"
    await message.answer(f"✅ SAVE MODE {status} для вашего аккаунта")