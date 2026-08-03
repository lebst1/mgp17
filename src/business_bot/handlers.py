import logging
import json
from aiogram import Router, F
from aiogram.types import Message, BusinessConnection, BusinessMessagesDeleted, CallbackQuery
from aiogram.filters import Command
from datetime import datetime
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository
from src.db.repositories.business_repository import BusinessRepository
from src.db.session import async_session
from src.config import settings

logger = logging.getLogger(__name__)

router = Router()


@router.business_connection()
async def handle_business_connection(event: BusinessConnection):
    """Обработчик подключения бизнес-аккаунта — ДЛЯ ЛЮБОГО ПОЛЬЗОВАТЕЛЯ"""
    user_id = event.user.id
    connection_id = event.connection_id
    
    logger.info(f"🔗 Business подключение: {connection_id}")
    logger.info(f"👤 Пользователь: {user_id}")
    logger.info(f"📊 Статус: {event.is_enabled}")
    
    # Создаем или обновляем пользователя
    user = await UserRepository.get_or_create(
        telegram_id=user_id,
        username=event.user.username,
        first_name=event.user.first_name,
        last_name=event.user.last_name
    )
    
    # Сохраняем подключение
    connection = await BusinessRepository.save_connection(
        connection_id=connection_id,
        user_telegram_id=user_id,
        is_enabled=event.is_enabled
    )
    
    # Отправляем приветствие владельцу
    await event.answer(
        "✅ Ваш бизнес-аккаунт подключен к Mnemora!\n\n"
        "Теперь я буду сохранять удаленные и отредактированные сообщения.\n"
        "Чтобы проверить статус, отправьте /business_status"
    )
    
    logger.info(f"✅ Пользователь {user_id} подключил бизнес-аккаунт")


@router.business_message()
async def handle_business_message(message: Message):
    """Обработчик новых бизнес-сообщений — ДЛЯ ЛЮБОГО ПОЛЬЗОВАТЕЛЯ"""
    if not message.from_user:
        return
    
    connection_id = message.business_connection_id
    if not connection_id:
        return
    
    # Получаем пользователя по connection_id
    user = await BusinessRepository.get_user_by_connection(connection_id)
    if not user:
        logger.warning(f"⚠️ Неизвестный connection_id: {connection_id}")
        return
    
    # Проверяем, включен ли SAVE MODE у пользователя
    if not user.savemode_enabled:
        return
    
    # Сохраняем сообщение
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
        
        # Если есть медиа
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


# ✅ ИСПРАВЛЕНО: используем правильный декоратор для удаленных сообщений
@router.business_messages_deleted()
async def handle_business_deleted(event: BusinessMessagesDeleted):
    """Обработчик удаленных бизнес-сообщений — ДЛЯ ЛЮБОГО ПОЛЬЗОВАТЕЛЯ"""
    connection_id = event.business_connection_id
    if not connection_id:
        return
    
    # Получаем пользователя по connection_id
    user = await BusinessRepository.get_user_by_connection(connection_id)
    if not user:
        logger.warning(f"⚠️ Неизвестный connection_id: {connection_id}")
        return
    
    logger.info(f"🗑 Удалены сообщения: {event.message_ids} в чате {event.chat.id} от {user.telegram_id}")
    
    # Для каждого удаленного сообщения
    for message_id in event.message_ids:
        try:
            # Помечаем сообщение как удаленное в БД
            await MessageRepository.mark_as_deleted(
                message_id=message_id,
                chat_id=event.chat.id,
                user_id=user.telegram_id
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки удаления: {e}")


@router.business_message(edited=True)
async def handle_business_edited(message: Message):
    """Обработчик отредактированных бизнес-сообщений — ДЛЯ ЛЮБОГО ПОЛЬЗОВАТЕЛЯ"""
    if not message.from_user:
        return
    
    connection_id = message.business_connection_id
    if not connection_id:
        return
    
    # Получаем пользователя по connection_id
    user = await BusinessRepository.get_user_by_connection(connection_id)
    if not user:
        return
    
    logger.info(f"✏️ Отредактировано сообщение {message.message_id} от {user.telegram_id}")
    
    # Обновляем сообщение в БД
    try:
        # Ищем существующее сообщение
        saved_msg = await MessageRepository.get_by_id(
            message_id=message.message_id,
            user_id=user.telegram_id
        )
        
        if saved_msg and saved_msg.text != message.text:
            # Сохраняем историю правок
            history = json.loads(saved_msg.edit_history) if saved_msg.edit_history else []
            history.append({
                "old_text": saved_msg.text,
                "new_text": message.text,
                "edited_at": datetime.utcnow().isoformat()
            })
            
            # Обновляем запись
            async with async_session() as session:
                saved_msg.text = message.text
                saved_msg.is_edited = True
                saved_msg.edit_history = json.dumps(history[-10:])  # Храним последние 10 правок
                await session.commit()
                
            logger.info(f"✅ Обновлена история правок для сообщения {message.message_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки правки: {e}")


@router.message(Command("business_status"))
async def business_status(message: Message):
    """Проверить статус бизнес-подключения — ДЛЯ ЛЮБОГО ПОЛЬЗОВАТЕЛЯ"""
    user = await UserRepository.get_by_id(message.from_user.id)
    
    # Получаем подключения пользователя
    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    
    status_text = f"""
📊 <b>Статус Business подключения</b>

👤 Пользователь: {user.first_name or user.username}
✅ Аккаунт: {'активен' if user.is_active else 'заблокирован'}
📝 SAVE MODE: {'✅ Включен' if user.savemode_enabled else '❌ Выключен'}
🔗 Подключений: {len(connections)}
📊 Сохранено сообщений: {user.messages_saved}

<b>Как проверить работу:</b>
1. Подключите бота в Настройки → Telegram Business → Чат-боты
2. Добавьте бота в чат как администратора
3. Удалите любое сообщение в чате
4. Бот сохранит его в базу данных

<b>Ограничения:</b>
• Бот видит только чаты, где он администратор
• Сообщения до подключения не сохраняются
"""
    
    if connections:
        status_text += f"\n<b>Активные подключения:</b>\n"
        for conn in connections:
            status_text += f"• {conn.connection_id[:20]}... {'✅ активен' if conn.is_enabled else '❌ отключен'}\n"
            if conn.connected_at:
                status_text += f"  Подключен: {conn.connected_at.strftime('%d.%m.%Y %H:%M')}\n"
            else:
                status_text += f"  Подключен: Неизвестно\n"
    
    await message.answer(status_text, parse_mode="HTML")


@router.message(Command("savemode"))
async def toggle_savemode(message: Message):
    """Включить/выключить SAVE MODE для пользователя"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "ℹ️ Использование: /savemode on - включить, /savemode off - выключить"
        )
        return
    
    action = args[1].lower()
    
    if action not in ["on", "off"]:
        await message.answer("❌ Используйте 'on' или 'off'")
        return
    
    enabled = action == "on"
    
    # Обновляем настройки пользователя
    user = await UserRepository.update_settings(
        message.from_user.id,
        savemode_enabled=enabled
    )
    
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        return
    
    status = "включен" if enabled else "выключен"
    await message.answer(f"✅ SAVE MODE {status} для вашего аккаунта")