from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository
from src.db.repositories.business_repository import BusinessRepository
from src.db.session import async_session, cleanup_old_data
from src.config import settings
from sqlalchemy import select, func, or_, and_, desc
from src.db.models import User, SavedMessage, BusinessConnection
import os
import logging
import time
import shutil
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = Router()

# ✅ ЛИМИТЫ
MAX_MEDIA_FILES = 50  # Максимум медиа в БД
MAX_MEDIA_AGE_DAYS = 1  # Хранить медиа 1


# ✅ СОСТОЯНИЯ ДЛЯ FSM
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()
    waiting_for_search = State()
    waiting_for_user_messages = State()
    waiting_for_view_media = State()


# ✅ ПРОВЕРКА АДМИНА
async def is_admin(user_id: int) -> bool:
    if user_id == settings.OWNER_TELEGRAM_ID:
        return True
    user = await UserRepository.get_by_id(user_id)
    return user.is_admin if user else False


# ✅ ГЛАВНОЕ МЕНЮ АДМИНА
async def show_admin_panel(target):
    text = """
🔐 <b>Админ панель SafeSaverX</b>

Выберите действие:

📊 <b>Статистика</b> — просмотр данных
📨 <b>Рассылка</b> — отправить сообщение всем
🔍 <b>Поиск пользователя</b> — найти по ID или username
🚫 <b>Бан</b> — заблокировать пользователя
✅ <b>Разбан</b> — разблокировать пользователя
📋 <b>Список пользователей</b> — все пользователи
📝 <b>Сообщения пользователя</b> — просмотр удаленных/правок
🗑️ <b>Очистка БД</b> — удалить старые данные
💾 <b>Бэкап</b> — создать бэкап
💚 <b>Статус</b> — состояние бота
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="admin_search")
        ],
        [
            InlineKeyboardButton(text="🚫 Бан", callback_data="admin_ban"),
            InlineKeyboardButton(text="✅ Разбан", callback_data="admin_unban")
        ],
        [
            InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="📝 Сообщения пользователя", callback_data="admin_user_messages")
        ],
        [
            InlineKeyboardButton(text="🗑️ Очистка БД", callback_data="admin_cleanup"),
            InlineKeyboardButton(text="💾 Бэкап", callback_data="admin_backup")
        ],
        [
            InlineKeyboardButton(text="💚 Статус", callback_data="admin_status")
        ]
    ])
    
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ панели.")
        return
    
    await show_admin_panel(message)


# ✅ СТАТИСТИКА
@router.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    async with async_session() as session:
        users_count = await session.scalar(select(func.count()).select_from(User))
        messages_count = await session.scalar(select(func.count()).select_from(SavedMessage))
        deleted_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.is_deleted == True)
        )
        edited_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.is_edited == True)
        )
        media_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.media_path.isnot(None))
        )
        connections_count = await session.scalar(select(func.count()).select_from(BusinessConnection))
    
    media_dir_size = 0
    media_files = 0
    if os.path.exists(settings.MEDIA_DIR):
        media_files = len(os.listdir(settings.MEDIA_DIR))
        for f in os.listdir(settings.MEDIA_DIR):
            f_path = os.path.join(settings.MEDIA_DIR, f)
            if os.path.isfile(f_path):
                media_dir_size += os.path.getsize(f_path)
    
    text = f"""
📊 <b>Статистика SafeSaverX</b>

👤 <b>Пользователи:</b> {users_count or 0}
📝 <b>Всего сообщений:</b> {messages_count or 0}
🗑️ <b>Удалено:</b> {deleted_count or 0}
✏️ <b>Отредактировано:</b> {edited_count or 0}
🖼️ <b>Медиа в БД:</b> {media_count or 0}
💾 <b>Медиа на диске:</b> {media_files} ({media_dir_size / 1024 / 1024:.1f} МБ)
🔗 <b>Бизнес-подключений:</b> {connections_count or 0}
"""
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]), parse_mode="HTML")
    await callback.answer()


# ✅ РАССЫЛКА
@router.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📨 <b>Рассылка</b>\n\n"
        "Отправь сообщение, которое нужно разослать всем пользователям.\n"
        "Это может быть текст, фото, видео.\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_back")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: Message, bot: Bot, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    async with async_session() as session:
        users = await session.scalars(select(User))
    
    count = 0
    for user in users:
        try:
            if message.text:
                await bot.send_message(chat_id=user.telegram_id, text=message.text, parse_mode="HTML")
            elif message.photo:
                await bot.send_photo(chat_id=user.telegram_id, photo=message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                await bot.send_video(chat_id=user.telegram_id, video=message.video.file_id, caption=message.caption)
            elif message.document:
                await bot.send_document(chat_id=user.telegram_id, document=message.document.file_id, caption=message.caption)
            count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user.telegram_id}: {e}")
    
    await message.answer(f"✅ Рассылка завершена! Отправлено {count} пользователям.")
    await state.clear()


# ✅ ПОИСК ПОЛЬЗОВАТЕЛЯ
@router.callback_query(lambda c: c.data == "admin_search")
async def admin_search(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Отправь ID пользователя или его @username для поиска.\n\n"
        "Пример: 123456789 или @username\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_search)
    await callback.answer()


@router.message(AdminStates.waiting_for_search)
async def process_search(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    query = message.text.strip()
    
    async with async_session() as session:
        if query.isdigit():
            user = await session.scalar(select(User).where(User.telegram_id == int(query)))
        else:
            username = query.replace('@', '')
            user = await session.scalar(select(User).where(User.username == username))
        
        if not user:
            await message.answer(f"❌ Пользователь не найден: {query}")
            await state.clear()
            return
        
        messages_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.user_id == user.telegram_id)
        )
        deleted_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(
                SavedMessage.user_id == user.telegram_id,
                SavedMessage.is_deleted == True
            )
        )
        edited_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(
                SavedMessage.user_id == user.telegram_id,
                SavedMessage.is_edited == True
            )
        )
    
    text = f"""
👤 <b>Найден пользователь</b>

🆔 ID: <code>{user.telegram_id}</code>
👤 Имя: {user.first_name or 'Не указано'}
📛 Юзернейм: @{user.username or 'Нет'}
✅ Активен: {'Да' if user.is_active else 'Нет'}
📝 Сообщений: {messages_count or 0}
🗑️ Удалено: {deleted_count or 0}
✏️ Отредактировано: {edited_count or 0}
📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Неизвестно'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Смотреть сообщения", callback_data=f"admin_view_user_{user.telegram_id}")
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"admin_ban_user_{user.telegram_id}"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin_unban_user_{user.telegram_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()


# ✅ ПРОСМОТР СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ
@router.callback_query(lambda c: c.data.startswith("admin_view_user_"))
async def admin_view_user_messages(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    await callback.message.edit_text(
        f"📝 <b>Сообщения пользователя {user_id}</b>\n\n"
        "Отправь:\n"
        "• <code>deleted</code> — показать удаленные сообщения\n"
        "• <code>edited</code> — показать отредактированные сообщения\n"
        "• <code>media</code> — показать сообщения с медиа\n"
        "• <code>all</code> — показать все сообщения\n\n"
        "Или отправь количество сообщений (например, 10).\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_messages)
    await state.update_data(user_id=user_id)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_messages)
async def process_user_messages(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('user_id')
    query = message.text.strip().lower()
    
    async with async_session() as session:
        stmt = select(SavedMessage).where(SavedMessage.user_id == user_id)
        
        if query == "deleted":
            stmt = stmt.where(SavedMessage.is_deleted == True)
            title = "🗑️ Удаленные сообщения"
        elif query == "edited":
            stmt = stmt.where(SavedMessage.is_edited == True)
            title = "✏️ Отредактированные сообщения"
        elif query == "media":
            stmt = stmt.where(SavedMessage.media_path.isnot(None))
            title = "🖼️ Сообщения с медиа"
        elif query == "all":
            title = "📝 Все сообщения"
        elif query.isdigit():
            limit = int(query)
            stmt = stmt.order_by(SavedMessage.saved_at.desc()).limit(limit)
            title = f"📝 Последние {limit} сообщений"
        else:
            await message.answer("❌ Неверный запрос. Используй: deleted, edited, media, all или число.")
            return
        
        if query in ["deleted", "edited", "media", "all"]:
            stmt = stmt.order_by(SavedMessage.saved_at.desc()).limit(20)
        
        messages = await session.scalars(stmt)
        messages = list(messages)
    
    if not messages:
        await message.answer(f"📭 Нет сообщений для этого запроса.")
        await state.clear()
        return
    
    for msg in messages:
        # Формируем текст для каждого сообщения
        text = f"""
<b>ID:</b> {msg.message_id}
📌 <b>Чат:</b> {msg.chat_title or msg.chat_id}
👤 <b>От:</b> @{msg.from_username or 'неизвестно'}
🕐 <b>Время:</b> {msg.saved_at.strftime('%d.%m.%Y %H:%M:%S')}
📝 <b>Текст:</b> {msg.text[:200] + '...' if msg.text and len(msg.text) > 200 else msg.text or 'Нет текста'}
{'🗑️ Удалено' if msg.is_deleted else ''}
{'✏️ Отредактировано' if msg.is_edited else ''}
{'🖼️ Медиа: ' + msg.media_type if msg.media_type else ''}
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼️ Показать медиа",
                    callback_data=f"admin_show_media_{msg.id}"
                )
            ]
        ]) if msg.media_path and os.path.exists(msg.media_path) else None
        
        if keyboard:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, parse_mode="HTML")
    
    await state.clear()


# ✅ ПОКАЗАТЬ МЕДИА
@router.callback_query(lambda c: c.data.startswith("admin_show_media_"))
async def admin_show_media(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    msg_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        msg = await session.scalar(select(SavedMessage).where(SavedMessage.id == msg_id))
        
        if not msg or not msg.media_path or not os.path.exists(msg.media_path):
            await callback.answer("❌ Медиа не найдено", show_alert=True)
            return
        
        try:
            media_file = FSInputFile(msg.media_path)
            
            if msg.media_type == "photo":
                await callback.message.answer_photo(photo=media_file)
            elif msg.media_type == "video":
                await callback.message.answer_video(video=media_file)
            elif msg.media_type in ["document", "file"]:
                await callback.message.answer_document(document=media_file)
            elif msg.media_type == "audio":
                await callback.message.answer_audio(audio=media_file)
            elif msg.media_type == "voice":
                await callback.message.answer_voice(voice=media_file)
            else:
                await callback.message.answer_document(document=media_file)
            
            # ✅ ОБНОВЛЯЕМ ВРЕМЯ ПОСЛЕДНЕГО ПРОСМОТРА
            # (чтобы не удалять недавно просмотренные)
            
        except Exception as e:
            await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
    
    await callback.answer()


# ✅ ОЧИСТКА СТАРЫХ МЕДИА
async def cleanup_old_media():
    """Удаляет медиа старше 1 дня"""
    try:
        async with async_session() as session:
            # Удаляем медиа старше 1 дня
            cutoff_date = datetime.utcnow() - timedelta(days=MAX_MEDIA_AGE_DAYS)
            
            media = await session.scalars(
                select(SavedMessage)
                .where(
                    SavedMessage.media_path.isnot(None),
                    SavedMessage.saved_at < cutoff_date
                )
            )
            
            deleted_count = 0
            for msg in media:
                if msg.media_path and os.path.exists(msg.media_path):
                    try:
                        os.remove(msg.media_path)
                        logger.info(f"🗑️ Удалён старый медиа-файл: {msg.media_path}")
                    except Exception as e:
                        logger.error(f"Ошибка удаления медиа: {e}")
                
                msg.media_path = None
                msg.media_type = None
                msg.media_file_id = None
                msg.media_size = None
                await session.merge(msg)
                deleted_count += 1
            
            await session.commit()
            logger.info(f"✅ Удалено {deleted_count} старых медиа (старше {MAX_MEDIA_AGE_DAYS} дня)")
            
    except Exception as e:
        logger.error(f"Ошибка очистки медиа: {e}")

# ✅ БАН
@router.callback_query(lambda c: c.data == "admin_ban")
async def admin_ban(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🚫 <b>Бан пользователя</b>\n\n"
        "Отправь ID пользователя, которого нужно заблокировать.\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.answer()


# ✅ БАН ПОЛЬЗОВАТЕЛЯ ИЗ ПОИСКА
@router.callback_query(lambda c: c.data.startswith("admin_ban_user_"))
async def admin_ban_user(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    user = await UserRepository.update_settings(user_id, is_active=False)
    
    if user:
        await callback.answer(f"✅ Пользователь {user_id} заблокирован!", show_alert=True)
    else:
        await callback.answer(f"❌ Пользователь {user_id} не найден!", show_alert=True)
    
    await show_user_info(callback, user_id)


# ✅ РАЗБАН ПОЛЬЗОВАТЕЛЯ ИЗ ПОИСКА
@router.callback_query(lambda c: c.data.startswith("admin_unban_user_"))
async def admin_unban_user(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    user = await UserRepository.update_settings(user_id, is_active=True)
    
    if user:
        await callback.answer(f"✅ Пользователь {user_id} разблокирован!", show_alert=True)
    else:
        await callback.answer(f"❌ Пользователь {user_id} не найден!", show_alert=True)
    
    await show_user_info(callback, user_id)


# ✅ НАЗАД К ПОЛЬЗОВАТЕЛЮ
@router.callback_query(lambda c: c.data.startswith("admin_back_to_user_"))
async def admin_back_to_user(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    await show_user_info(callback, user_id)


async def show_user_info(callback: CallbackQuery, user_id: int):
    """Показывает информацию о пользователе"""
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        messages_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.user_id == user.telegram_id)
        )
    
    text = f"""
👤 <b>Пользователь</b>

🆔 ID: <code>{user.telegram_id}</code>
👤 Имя: {user.first_name or 'Не указано'}
📛 Юзернейм: @{user.username or 'Нет'}
✅ Активен: {'Да' if user.is_active else 'Нет'}
📝 Сообщений: {messages_count or 0}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Смотреть сообщения", callback_data=f"admin_view_user_{user.telegram_id}")
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"admin_ban_user_{user.telegram_id}"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin_unban_user_{user.telegram_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ РАЗБАН
@router.callback_query(lambda c: c.data == "admin_unban")
async def admin_unban(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "✅ <b>Разбан пользователя</b>\n\n"
        "Отправь ID пользователя, которого нужно разблокировать.\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id)
async def process_ban_unban(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
        user = await UserRepository.get_by_id(user_id)
        if user:
            new_status = not user.is_active
            user = await UserRepository.update_settings(user_id, is_active=new_status)
            status_text = "разблокирован" if new_status else "заблокирован"
            await message.answer(f"✅ Пользователь {user_id} {status_text}!")
        else:
            await message.answer(f"❌ Пользователь {user_id} не найден.")
    except ValueError:
        await message.answer("❌ Неверный формат. Отправь числовой ID.")
    
    await state.clear()


# ✅ СПИСОК ПОЛЬЗОВАТЕЛЕЙ
@router.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    async with async_session() as session:
        users = await session.scalars(select(User).limit(20).order_by(User.created_at.desc()))
    
    text = "📋 <b>Последние 20 пользователей:</b>\n\n"
    for user in users:
        text += f"👤 {user.telegram_id} | {user.first_name or user.username or 'No name'} | {'✅' if user.is_active else '🚫'}\n"
    
    if len(text) > 4000:
        text = text[:4000] + "\n... и еще"
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]), parse_mode="HTML")
    await callback.answer()


# ✅ ОЧИСТКА БД
@router.callback_query(lambda c: c.data == "admin_cleanup")
async def admin_cleanup(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text("🧹 <b>Очистка БД...</b>", parse_mode="HTML")
    
    try:
        await cleanup_old_data()
        await cleanup_old_media()  # ✅ Очистка старых медиа
        await callback.message.edit_text("✅ Очистка БД и медиа завершена!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]), parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка очистки: {e}", parse_mode="HTML")
    
    await callback.answer()


# ✅ БЭКАП
@router.callback_query(lambda c: c.data == "admin_backup")
async def admin_backup(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    from datetime import datetime
    import shutil
    
    try:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        date = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if os.path.exists("data/app.db"):
            shutil.copy2("data/app.db", f"{backup_dir}/app_{date}.db")
            await callback.message.edit_text(
                f"✅ Бэкап создан: app_{date}.db",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
                ]),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text("❌ Файл БД не найден!", parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка бэкапа: {e}", parse_mode="HTML")
    
    await callback.answer()


# ✅ СТАТУС
@router.callback_query(lambda c: c.data == "admin_status")
async def admin_status(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    import psutil
    
    db_size = 0
    if os.path.exists("data/app.db"):
        db_size = os.path.getsize("data/app.db") / 1024 / 1024
    
    media_size = 0
    media_files = 0
    if os.path.exists(settings.MEDIA_DIR):
        media_files = len(os.listdir(settings.MEDIA_DIR))
        for f in os.listdir(settings.MEDIA_DIR):
            f_path = os.path.join(settings.MEDIA_DIR, f)
            if os.path.isfile(f_path):
                media_size += os.path.getsize(f_path)
    
    text = f"""
💚 <b>Статус SafeSaverX</b>

📌 Режим: {settings.TELEGRAM_MODE}
👤 Владелец: {settings.OWNER_TELEGRAM_ID}

<b>Система:</b>
🧠 RAM: {psutil.virtual_memory().percent}%
💾 Диск: {psutil.disk_usage('/').percent}%
🔄 Uptime: {int((time.time() - psutil.boot_time()) / 3600)}ч

<b>База данных:</b>
📁 Размер: {db_size:.1f} МБ

<b>Медиа:</b>
💾 Файлов: {media_files} ({media_size / 1024 / 1024:.1f} МБ)
📦 Лимит: {MAX_MEDIA_FILES} файлов
"""
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]), parse_mode="HTML")
    await callback.answer()


# ✅ НАЗАД
@router.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.answer()
    await show_admin_panel(callback)


# ✅ КОМАНДА /cancel
@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.")