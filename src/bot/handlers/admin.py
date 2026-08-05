from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile, BufferedInputFile
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
from sqlalchemy import select, func, or_, and_, desc, case
import io

logger = logging.getLogger(__name__)

router = Router()

MAX_MEDIA_FILES = 50
MAX_MEDIA_AGE_DAYS = 1


# ✅ СОСТОЯНИЯ ДЛЯ FSM
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()
    waiting_for_search = State()
    waiting_for_user_messages = State()
    waiting_for_view_media = State()
    waiting_for_chat_view = State()
    waiting_for_chat_select = State()
    waiting_for_chat_search = State()
    waiting_for_chat_message = State()


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
💬 <b>Чаты пользователя</b> — просмотр всех чатов
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
            InlineKeyboardButton(text="💬 Чаты пользователя", callback_data="admin_chats")
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
        
        # Получаем список чатов пользователя
        chats = await session.execute(
            select(
                SavedMessage.chat_id,
                SavedMessage.chat_title,
                func.count(SavedMessage.id).label('count'),
                func.max(SavedMessage.saved_at).label('last_activity')
            )
            .where(SavedMessage.user_id == user.telegram_id)
            .group_by(SavedMessage.chat_id, SavedMessage.chat_title)
            .order_by(func.max(SavedMessage.saved_at).desc())
        )
        chats = chats.all()
        
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
💬 Чатов: {len(chats)}
📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Неизвестно'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Список чатов", callback_data=f"admin_chats_user_{user.telegram_id}")
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


# ✅ СПИСОК ЧАТОВ ПОЛЬЗОВАТЕЛЯ
@router.callback_query(lambda c: c.data.startswith("admin_chats_user_"))
async def admin_chats_user(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    await show_chats_list(callback.message, user_id)
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_chats")
async def admin_chats(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💬 <b>Чаты пользователя</b>\n\n"
        "Отправь ID пользователя, чтобы увидеть список его чатов.\n\n"
        "Или отправь <b>поиск: текст</b> чтобы найти чат по названию.\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_chat_select)
    await callback.answer()


@router.message(AdminStates.waiting_for_chat_select)
async def process_chat_select(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    text = message.text.strip()
    
    if text.lower().startswith("поиск:") or text.lower().startswith("search:"):
        search_query = text.split(":", 1)[1].strip()
        await show_chats_search(message, search_query)
        await state.clear()
        return
    
    try:
        user_id = int(text)
        await show_chats_list(message, user_id)
    except ValueError:
        await message.answer("❌ Неверный формат. Отправь ID пользователя или 'поиск: название'.")
    
    await state.clear()


async def show_chats_search(target, search_query: str):
    """Поиск чатов по названию"""
    
    async with async_session() as session:
        chats = await session.execute(
            select(
                SavedMessage.user_id,
                SavedMessage.chat_id,
                SavedMessage.chat_title,
                func.count(SavedMessage.id).label('count'),
                func.max(SavedMessage.saved_at).label('last_activity')
            )
            .where(SavedMessage.chat_title.ilike(f"%{search_query}%"))
            .group_by(SavedMessage.user_id, SavedMessage.chat_id, SavedMessage.chat_title)
            .order_by(func.max(SavedMessage.saved_at).desc())
            .limit(30)
        )
        chats = chats.all()
    
    if not chats:
        await target.answer(f"❌ Чаты с названием '{search_query}' не найдены.")
        return
    
    text = f"""
🔍 <b>Результаты поиска чатов</b>
По запросу: <i>"{search_query}"</i>
Найдено: {len(chats)}

➖➖➖➖➖➖➖➖➖➖➖➖
"""
    
    keyboard_buttons = []
    
    for chat in chats:
        chat_title = chat.chat_title or f"Чат {chat.chat_id}"
        if len(chat_title) > 25:
            chat_title = chat_title[:22] + "..."
        
        button_text = f"👤 {chat.user_id} | {chat_title} ({chat.count})"
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"admin_chat_open_{chat.user_id}_{chat.chat_id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


from sqlalchemy import case  # ✅ ДОБАВИТЬ В НАЧАЛЕ ФАЙЛА

async def show_chats_list(target, user_id: int):
    """Показывает список всех чатов пользователя"""
    
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await target.answer("❌ Пользователь не найден")
            return
        
        # ✅ ИСПРАВЛЕНО: правильный синтаксис case()
        deleted_count = func.sum(
            case((SavedMessage.is_deleted == True, 1), else_=0)
        ).label('deleted_count')
        
        edited_count = func.sum(
            case((SavedMessage.is_edited == True, 1), else_=0)
        ).label('edited_count')
        
        chats = await session.execute(
            select(
                SavedMessage.chat_id,
                SavedMessage.chat_title,
                func.count(SavedMessage.id).label('count'),
                func.max(SavedMessage.saved_at).label('last_activity'),
                deleted_count,
                edited_count
            )
            .where(SavedMessage.user_id == user_id)
            .group_by(SavedMessage.chat_id, SavedMessage.chat_title)
            .order_by(func.max(SavedMessage.saved_at).desc())
        )
        chats = chats.all()
    
    if not chats:
        await target.answer("📭 Нет сохранённых чатов у этого пользователя.")
        return
    
    text = f"""
💬 <b>Чаты пользователя</b>

👤 <b>{user.first_name or user.username or 'Пользователь'}</b>
🆔 <code>{user.telegram_id}</code>
📊 <b>Всего чатов:</b> {len(chats)}

➖➖➖➖➖➖➖➖➖➖➖➖
"""
    
    keyboard_buttons = []
    
    for chat in chats:
        chat_title = chat.chat_title or f"Чат {chat.chat_id}"
        if len(chat_title) > 20:
            chat_title = chat_title[:17] + "..."
        
        status = ""
        if chat.deleted_count and chat.deleted_count > 0:
            status += f"🗑️{chat.deleted_count} "
        if chat.edited_count and chat.edited_count > 0:
            status += f"✏️{chat.edited_count} "
        
        button_text = f"💬 {chat_title} ({chat.count}) {status}".strip()
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"admin_chat_open_{user_id}_{chat.chat_id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="🔍 Поиск по чатам",
            callback_data=f"admin_chat_search_{user_id}"
        ),
        InlineKeyboardButton(
            text="📊 Статистика чатов",
            callback_data=f"admin_chat_stats_{user_id}"
        )
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ ПОИСК ПО ЧАТАМ ПОЛЬЗОВАТЕЛЯ
@router.callback_query(lambda c: c.data.startswith("admin_chat_search_"))
async def admin_chat_search_user(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    await callback.message.edit_text(
        f"🔍 <b>Поиск чата у пользователя {user_id}</b>\n\n"
        f"Отправь название чата для поиска.\n\n"
        f"Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_chat_search)
    await state.update_data(user_id=user_id)
    await callback.answer()


@router.message(AdminStates.waiting_for_chat_search)
async def process_chat_search(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('user_id')
    search_query = message.text.strip()
    
    async with async_session() as session:
        chats = await session.execute(
            select(
                SavedMessage.chat_id,
                SavedMessage.chat_title,
                func.count(SavedMessage.id).label('count'),
                func.max(SavedMessage.saved_at).label('last_activity')
            )
            .where(
                SavedMessage.user_id == user_id,
                SavedMessage.chat_title.ilike(f"%{search_query}%")
            )
            .group_by(SavedMessage.chat_id, SavedMessage.chat_title)
            .order_by(func.max(SavedMessage.saved_at).desc())
            .limit(20)
        )
        chats = chats.all()
    
    if not chats:
        await message.answer(f"❌ Чаты с названием '{search_query}' не найдены.")
        await state.clear()
        return
    
    text = f"""
🔍 <b>Результаты поиска у пользователя {user_id}</b>
По запросу: <i>"{search_query}"</i>
Найдено: {len(chats)}

➖➖➖➖➖➖➖➖➖➖➖➖
"""
    
    keyboard_buttons = []
    
    for chat in chats:
        chat_title = chat.chat_title or f"Чат {chat.chat_id}"
        if len(chat_title) > 25:
            chat_title = chat_title[:22] + "..."
        
        button_text = f"💬 {chat_title} ({chat.count})"
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"admin_chat_open_{user_id}_{chat.chat_id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="🔙 Назад к чатам",
            callback_data=f"admin_chats_user_{user_id}"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()


# ✅ СТАТИСТИКА ЧАТОВ ПОЛЬЗОВАТЕЛЯ
@router.callback_query(lambda c: c.data.startswith("admin_chat_stats_"))
@router.callback_query(lambda c: c.data.startswith("admin_chat_stats_"))
async def admin_chat_stats(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        total_messages = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.user_id == user_id)
        )
        total_deleted = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(
                SavedMessage.user_id == user_id,
                SavedMessage.is_deleted == True
            )
        )
        total_edited = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(
                SavedMessage.user_id == user_id,
                SavedMessage.is_edited == True
            )
        )
        total_media = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(
                SavedMessage.user_id == user_id,
                SavedMessage.media_path.isnot(None)
            )
        )
        
        # ✅ ИСПРАВЛЕНО: правильный синтаксис case()
        deleted_sum = func.sum(
            case((SavedMessage.is_deleted == True, 1), else_=0)
        ).label('deleted')
        
        edited_sum = func.sum(
            case((SavedMessage.is_edited == True, 1), else_=0)
        ).label('edited')
        
        media_sum = func.sum(
            case((SavedMessage.media_path.isnot(None), 1), else_=0)
        ).label('media')
        
        chats = await session.execute(
            select(
                SavedMessage.chat_title,
                func.count(SavedMessage.id).label('count'),
                deleted_sum,
                edited_sum,
                media_sum
            )
            .where(SavedMessage.user_id == user_id)
            .group_by(SavedMessage.chat_title)
            .order_by(func.count(SavedMessage.id).desc())
            .limit(10)
        )
        chats = chats.all()
    
    text = f"""
📊 <b>Статистика чатов</b>
👤 Пользователь: <code>{user_id}</code>

📝 <b>Всего сообщений:</b> {total_messages or 0}
🗑️ <b>Удалено:</b> {total_deleted or 0}
✏️ <b>Отредактировано:</b> {total_edited or 0}
🖼️ <b>Медиа:</b> {total_media or 0}

<b>Топ чатов:</b>
"""
    
    for i, chat in enumerate(chats, 1):
        chat_title = chat.chat_title or "Без названия"
        if len(chat_title) > 20:
            chat_title = chat_title[:17] + "..."
        text += f"{i}. {chat_title}: {chat.count} сообщ. (🗑️{chat.deleted or 0} ✏️{chat.edited or 0} 🖼️{chat.media or 0})\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💬 К чатам",
                callback_data=f"admin_chats_user_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ✅ ОТКРЫТЬ КОНКРЕТНЫЙ ЧАТ
@router.callback_query(lambda c: c.data.startswith("admin_chat_open_"))
async def admin_chat_open(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    
    await show_chat_messages(callback.message, user_id, chat_id)
    await callback.answer()


# ✅ ОТПРАВИТЬ СООБЩЕНИЕ В ЧАТ
@router.callback_query(lambda c: c.data.startswith("admin_chat_send_"))
async def admin_chat_send(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    
    await callback.message.edit_text(
        f"📨 <b>Отправить сообщение в чат</b>\n\n"
        f"Пользователь: <code>{user_id}</code>\n"
        f"Чат: <code>{chat_id}</code>\n\n"
        f"Отправь текст сообщения для отправки в этот чат.\n\n"
        f"Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_chat_message)
    await state.update_data(user_id=user_id, chat_id=chat_id)
    await callback.answer()


@router.message(AdminStates.waiting_for_chat_message)
async def process_chat_message(message: Message, bot: Bot, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    data = await state.get_data()
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    
    try:
        if message.text:
            await bot.send_message(chat_id=chat_id, text=message.text, parse_mode="HTML")
            await message.answer(f"✅ Сообщение отправлено в чат {chat_id}")
        elif message.photo:
            await bot.send_photo(chat_id=chat_id, photo=message.photo[-1].file_id, caption=message.caption)
            await message.answer(f"✅ Фото отправлено в чат {chat_id}")
        elif message.video:
            await bot.send_video(chat_id=chat_id, video=message.video.file_id, caption=message.caption)
            await message.answer(f"✅ Видео отправлено в чат {chat_id}")
        else:
            await message.answer("❌ Неподдерживаемый тип сообщения")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")
    
    await state.clear()


# ✅ ЭКСПОРТ ЧАТА
@router.callback_query(lambda c: c.data.startswith("admin_chat_export_"))
async def admin_chat_export(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    
    async with async_session() as session:
        messages = await session.scalars(
            select(SavedMessage)
            .where(
                SavedMessage.user_id == user_id,
                SavedMessage.chat_id == chat_id
            )
            .order_by(SavedMessage.saved_at)
        )
        messages = list(messages)
    
    if not messages:
        await callback.answer("📭 Нет сообщений для экспорта", show_alert=True)
        return
    
    chat_title = messages[0].chat_title or f"чат_{chat_id}"
    export_text = f"Экспорт чата: {chat_title}\n"
    export_text += f"Пользователь: {user_id}\n"
    export_text += f"Всего сообщений: {len(messages)}\n"
    export_text += "=" * 50 + "\n\n"
    
    for msg in messages:
        time_str = msg.saved_at.strftime('%Y-%m-%d %H:%M:%S')
        name = msg.from_username or msg.from_first_name or 'Аноним'
        export_text += f"[{time_str}] {name}:\n"
        if msg.text:
            export_text += f"{msg.text}\n"
        if msg.media_type:
            export_text += f"[Медиа: {msg.media_type}]\n"
        if msg.is_deleted:
            export_text += "[УДАЛЕНО]\n"
        if msg.is_edited:
            export_text += "[ОТРЕДАКТИРОВАНО]\n"
        export_text += "-" * 30 + "\n"
    
    file_data = BufferedInputFile(
        export_text.encode('utf-8'),
        filename=f"chat_{user_id}_{chat_id}.txt"
    )
    
    await callback.message.answer_document(
        document=file_data,
        caption=f"📄 Экспорт чата {chat_title}\nСообщений: {len(messages)}"
    )
    
    await show_chat_messages(callback.message, user_id, chat_id)
    await callback.answer()


async def send_chat_part(target, text, user_id, chat_id, filter_type, total):
    """Отправляет часть сообщения с кнопкой продолжения"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📥 Продолжить",
                callback_data=f"admin_chat_more_{user_id}_{chat_id}_30"
            )
        ]
    ])
    await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ ФИЛЬТР В ЧАТЕ
@router.callback_query(lambda c: c.data.startswith("admin_chat_filter_"))
async def admin_chat_filter(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    filter_type = parts[5]
    
    if filter_type == "all":
        filter_type = None
    
    await show_chat_messages(callback.message, user_id, chat_id, filter_type)
    await callback.answer()


# ✅ ПОКАЗАТЬ ВСЕ МЕДИА В ЧАТЕ
@router.callback_query(lambda c: c.data.startswith("admin_chat_media_"))
async def admin_chat_media(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    
    async with async_session() as session:
        messages = await session.scalars(
            select(SavedMessage)
            .where(
                SavedMessage.user_id == user_id,
                SavedMessage.chat_id == chat_id,
                SavedMessage.media_path.isnot(None)
            )
            .order_by(SavedMessage.saved_at.desc())
            .limit(20)
        )
        messages = list(messages)
    
    if not messages:
        await callback.answer("📭 Нет медиа в этом чате", show_alert=True)
        return
    
    await callback.message.answer(f"🖼️ <b>Все медиа в чате ({len(messages)})</b>", parse_mode="HTML")
    
    for msg in messages:
        try:
            if not msg.media_path or not os.path.exists(msg.media_path):
                continue
                
            media_file = FSInputFile(msg.media_path)
            caption = f"📎 <b>{msg.media_type}</b>\n🕐 {msg.saved_at.strftime('%d.%m.%Y %H:%M')}"
            
            if msg.text:
                caption += f"\n📝 {msg.text[:100]}{'...' if len(msg.text) > 100 else ''}"
            
            if msg.is_deleted:
                caption += "\n🗑️ Удалено"
            if msg.is_edited:
                caption += "\n✏️ Отредактировано"
            
            if msg.media_type == "photo":
                await callback.message.answer_photo(photo=media_file, caption=caption, parse_mode="HTML")
            elif msg.media_type == "video":
                await callback.message.answer_video(video=media_file, caption=caption, parse_mode="HTML")
            elif msg.media_type == "document":
                await callback.message.answer_document(document=media_file, caption=caption, parse_mode="HTML")
            elif msg.media_type == "audio":
                await callback.message.answer_audio(audio=media_file, caption=caption, parse_mode="HTML")
            elif msg.media_type == "voice":
                await callback.message.answer_voice(voice=media_file, caption=caption, parse_mode="HTML")
            elif msg.media_type == "sticker":
                await callback.message.answer_sticker(sticker=media_file)
            else:
                await callback.message.answer_document(document=media_file, caption=caption, parse_mode="HTML")
                
        except Exception as e:
            logger.error(f"Ошибка отправки медиа {msg.id}: {e}")
            continue
    
    await show_chat_messages(callback.message, user_id, chat_id)
    await callback.answer()


# ✅ ПОКАЗАТЬ ЕЩЁ СООБЩЕНИЯ
@router.callback_query(lambda c: c.data.startswith("admin_chat_more_"))
async def admin_chat_more(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    offset = int(parts[5]) if len(parts) > 5 else 30
    
    async with async_session() as session:
        messages = await session.scalars(
            select(SavedMessage)
            .where(
                SavedMessage.user_id == user_id,
                SavedMessage.chat_id == chat_id
            )
            .order_by(SavedMessage.saved_at.desc())
            .offset(offset)
            .limit(30)
        )
        messages = list(messages)
    
    if not messages:
        await callback.answer("📭 Больше сообщений нет", show_alert=True)
        return
    
    chat_text = ""
    for msg in reversed(messages):
        time_str = msg.saved_at.strftime('%d.%m %H:%M')
        name = msg.from_username or msg.from_first_name or 'Аноним'
        
        if msg.from_user_id == user_id:
            chat_text += f"\n👤 <b>{name}</b> [{time_str}]:\n"
        else:
            chat_text += f"\n🤖 <b>{name}</b> [{time_str}]:\n"
        
        if msg.text:
            text_preview = msg.text[:300]
            if len(msg.text) > 300:
                text_preview += "..."
            chat_text += f"{text_preview}\n"
        
        if msg.media_type:
            chat_text += f"🖼️ <i>[{msg.media_type}]</i>\n"
        
        chat_text += "➖➖➖➖➖➖➖➖➖➖\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📥 Ещё",
                callback_data=f"admin_chat_more_{user_id}_{chat_id}_{offset + 30}"
            )
        ],
        [
            InlineKeyboardButton(text="🔙 Назад к чату", callback_data=f"admin_chat_open_{user_id}_{chat_id}")
        ]
    ])
    
    await callback.message.answer(chat_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


async def show_chat_messages(target, user_id: int, chat_id: int, filter_type: str = None):
    """Показывает сообщения в конкретном чате с возможностью просмотра медиа"""
    
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await target.answer("❌ Пользователь не найден")
            return
        
        chat_title = await session.scalar(
            select(SavedMessage.chat_title)
            .where(
                SavedMessage.user_id == user_id,
                SavedMessage.chat_id == chat_id
            )
            .limit(1)
        )
        
        stmt = select(SavedMessage).where(
            SavedMessage.user_id == user_id,
            SavedMessage.chat_id == chat_id
        )
        
        if filter_type == "deleted":
            stmt = stmt.where(SavedMessage.is_deleted == True)
        elif filter_type == "edited":
            stmt = stmt.where(SavedMessage.is_edited == True)
        elif filter_type == "media":
            stmt = stmt.where(SavedMessage.media_path.isnot(None))
        
        total_count = await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        
        messages = await session.scalars(
            stmt.order_by(SavedMessage.saved_at.desc()).limit(30)
        )
        messages = list(messages)
    
    chat_title_display = chat_title or f"Чат {chat_id}"
    
    filter_text = ""
    if filter_type == "deleted":
        filter_text = " 🗑️ (только удаленные)"
    elif filter_type == "edited":
        filter_text = " ✏️ (только правки)"
    elif filter_type == "media":
        filter_text = " 🖼️ (только медиа)"
    
    header = f"""
💬 <b>Чат: {chat_title_display}</b>{filter_text}

👤 <b>{user.first_name or user.username or 'Пользователь'}</b>
🆔 <code>{user.telegram_id}</code>
💬 ID чата: <code>{chat_id}</code>
📊 <b>Показано:</b> {len(messages)} из {total_count}

➖➖➖➖➖➖➖➖➖➖➖➖
"""
    
    chat_text = header
    media_items = []
    
    for msg in reversed(messages):
        time_str = msg.saved_at.strftime('%d.%m %H:%M')
        name = msg.from_username or msg.from_first_name or 'Аноним'
        
        if msg.from_user_id == user_id:
            chat_text += f"\n👤 <b>{name}</b> [{time_str}]:\n"
        else:
            chat_text += f"\n🤖 <b>{name}</b> [{time_str}]:\n"
        
        if msg.text:
            text_preview = msg.text[:300]
            if len(msg.text) > 300:
                text_preview += "..."
            chat_text += f"{text_preview}\n"
        
        if msg.media_type:
            media_emoji = {
                "photo": "🖼️",
                "video": "🎬",
                "document": "📄",
                "audio": "🎵",
                "voice": "🎤",
                "sticker": "🎨"
            }
            emoji = media_emoji.get(msg.media_type, "📎")
            chat_text += f"{emoji} <i>[{msg.media_type}]</i>"
            
            if msg.media_path and os.path.exists(msg.media_path):
                chat_text += f" <i>({os.path.getsize(msg.media_path) / 1024:.1f} КБ)</i>"
                media_items.append(msg)
        
        status = []
        if msg.is_deleted:
            status.append("🗑️ Удалено")
        if msg.is_edited:
            status.append("✏️ Отредактировано")
        if status:
            chat_text += f"\n<i>{' '.join(status)}</i>"
        
        chat_text += "\n➖➖➖➖➖➖➖➖➖➖\n"
        
        if len(chat_text) > 3800:
            await send_chat_part(target, chat_text, user_id, chat_id, filter_type, len(messages))
            chat_text = header
    
    # Отправляем медиа отдельно
    if media_items:
        await target.answer("🖼️ <b>Медиа в этом чате:</b>", parse_mode="HTML")
        for msg in media_items[:10]:
            try:
                media_file = FSInputFile(msg.media_path)
                caption = f"📎 <b>{msg.media_type}</b>\n🕐 {msg.saved_at.strftime('%d.%m.%Y %H:%M')}"
                
                if msg.text:
                    caption += f"\n📝 {msg.text[:100]}{'...' if len(msg.text) > 100 else ''}"
                
                if msg.media_type == "photo":
                    await target.answer_photo(photo=media_file, caption=caption, parse_mode="HTML")
                elif msg.media_type == "video":
                    await target.answer_video(video=media_file, caption=caption, parse_mode="HTML")
                elif msg.media_type == "document":
                    await target.answer_document(document=media_file, caption=caption, parse_mode="HTML")
                elif msg.media_type == "audio":
                    await target.answer_audio(audio=media_file, caption=caption, parse_mode="HTML")
                elif msg.media_type == "voice":
                    await target.answer_voice(voice=media_file, caption=caption, parse_mode="HTML")
                elif msg.media_type == "sticker":
                    await target.answer_sticker(sticker=media_file)
                else:
                    await target.answer_document(document=media_file, caption=caption, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка отправки медиа {msg.id}: {e}")
    
    # Отправляем последнюю часть с кнопками
    keyboard_buttons = [
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin_chat_open_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="🗑️ Удалить чат", callback_data=f"admin_chat_delete_{user_id}_{chat_id}")
        ],
        [
            InlineKeyboardButton(text="📨 Отправить сообщение", callback_data=f"admin_chat_send_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="📄 Экспорт", callback_data=f"admin_chat_export_{user_id}_{chat_id}")
        ],
        [
            InlineKeyboardButton(text="🖼️ Все медиа", callback_data=f"admin_chat_media_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="📥 Показать ещё", callback_data=f"admin_chat_more_{user_id}_{chat_id}_{30}")
        ],
        [
            InlineKeyboardButton(text="📝 Все", callback_data=f"admin_chat_filter_{user_id}_{chat_id}_all"),
            InlineKeyboardButton(text="🗑️ Удаленные", callback_data=f"admin_chat_filter_{user_id}_{chat_id}_deleted")
        ],
        [
            InlineKeyboardButton(text="✏️ Правки", callback_data=f"admin_chat_filter_{user_id}_{chat_id}_edited"),
            InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"admin_chat_filter_{user_id}_{chat_id}_media")
        ],
        [
            InlineKeyboardButton(text="💬 Список чатов", callback_data=f"admin_chats_user_{user_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await target.answer(chat_text, reply_markup=keyboard, parse_mode="HTML")


# ✅ УДАЛИТЬ ВЕСЬ ЧАТ
@router.callback_query(lambda c: c.data.startswith("admin_chat_delete_"))
async def admin_chat_delete(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить чат", callback_data=f"admin_chat_delete_confirm_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_chat_open_{user_id}_{chat_id}")
        ]
    ])
    
    await callback.message.edit_text(
        f"⚠️ <b>Удалить весь чат?</b>\n\n"
        f"Пользователь: {user_id}\n"
        f"Чат: {chat_id}\n\n"
        f"Это действие необратимо!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("admin_chat_delete_confirm_"))
async def admin_chat_delete_confirm(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[4])
    chat_id = int(parts[5])
    
    async with async_session() as session:
        messages = await session.scalars(
            select(SavedMessage).where(
                SavedMessage.user_id == user_id,
                SavedMessage.chat_id == chat_id
            )
        )
        
        deleted_count = 0
        for msg in messages:
            if msg.media_path and os.path.exists(msg.media_path):
                try:
                    os.remove(msg.media_path)
                except:
                    pass
            await session.delete(msg)
            deleted_count += 1
        
        await session.commit()
    
    await callback.message.edit_text(
        f"✅ Удалено {deleted_count} сообщений из чата {chat_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Список чатов", callback_data=f"admin_chats_user_{user_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


# ✅ БАН ПОЛЬЗОВАТЕЛЯ
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


# ✅ РАЗБАН ПОЛЬЗОВАТЕЛЯ
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


# ✅ ОЧИСТКА СТАРЫХ МЕДИА
async def cleanup_old_media():
    try:
        async with async_session() as session:
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


# ✅ ОЧИСТКА БД
@router.callback_query(lambda c: c.data == "admin_cleanup")
async def admin_cleanup(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text("🧹 <b>Очистка БД...</b>", parse_mode="HTML")
    
    try:
        await cleanup_old_data()
        await cleanup_old_media()
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