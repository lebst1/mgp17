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
💬 <b>Чат пользователя</b> — просмотр переписки
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
            InlineKeyboardButton(text="💬 Чат пользователя", callback_data="admin_chat")
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
            InlineKeyboardButton(text="💬 Открыть чат", callback_data=f"admin_chat_user_{user.telegram_id}")
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


# ✅ ЧАТ ПОЛЬЗОВАТЕЛЯ (НОВЫЙ ИНТЕРФЕЙС)
@router.callback_query(lambda c: c.data == "admin_chat")
async def admin_chat(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💬 <b>Чат пользователя</b>\n\n"
        "Отправь ID пользователя, чей чат хочешь посмотреть.\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_chat_view)
    await callback.answer()


@router.message(AdminStates.waiting_for_chat_view)
async def process_chat_view(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
        await show_chat_interface(message, user_id)
    except ValueError:
        await message.answer("❌ Неверный формат. Отправь числовой ID.")
    
    await state.clear()


@router.callback_query(lambda c: c.data.startswith("admin_chat_user_"))
async def admin_chat_user(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    await show_chat_interface(callback.message, user_id)
    await callback.answer()


async def show_chat_interface(target, user_id: int):
    """Показывает чат пользователя в виде диалога"""
    
    async with async_session() as session:
        # Получаем пользователя
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await target.answer("❌ Пользователь не найден")
            return
        
        # Получаем сообщения пользователя (последние 30)
        messages = await session.scalars(
            select(SavedMessage)
            .where(SavedMessage.user_id == user_id)
            .order_by(SavedMessage.saved_at.desc())
            .limit(30)
        )
        messages = list(messages)
    
    # Формируем заголовок чата
    header = f"""
💬 <b>Чат пользователя</b>

👤 <b>{user.first_name or user.username or 'Пользователь'}</b>
🆔 <code>{user.telegram_id}</code>
📊 <b>Всего сообщений:</b> {len(messages)}
📅 <b>Активен:</b> {'✅ Да' if user.is_active else '❌ Нет'}

➖➖➖➖➖➖➖➖➖➖➖➖
"""
    
    # Формируем сообщения как в чате
    chat_text = header
    for msg in reversed(messages):  # От старых к новым
        time_str = msg.saved_at.strftime('%H:%M')
        name = msg.from_username or msg.from_first_name or 'Аноним'
        
        # Определяем, чье сообщение
        if msg.from_user_id == user.telegram_id:
            # Сообщение пользователя
            chat_text += f"\n👤 <b>{name}</b> [{time_str}]:\n"
        else:
            # Сообщение от другого пользователя
            chat_text += f"\n🤖 <b>{name}</b> [{time_str}]:\n"
        
        # Текст сообщения
        if msg.text:
            text_preview = msg.text[:500]
            if len(msg.text) > 500:
                text_preview += "..."
            chat_text += f"{text_preview}\n"
        
        # Медиа
        if msg.media_type:
            chat_text += f"🖼️ <i>[{msg.media_type}]</i>\n"
        
        # Статус
        status = []
        if msg.is_deleted:
            status.append("🗑️ Удалено")
        if msg.is_edited:
            status.append("✏️ Отредактировано")
        if status:
            chat_text += f"<i>{' '.join(status)}</i>\n"
        
        chat_text += "➖➖➖➖➖➖➖➖➖➖\n"
        
        # Если текст слишком длинный — разбиваем
        if len(chat_text) > 3800:
            # Отправляем текущую часть
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📥 Показать ещё",
                        callback_data=f"admin_chat_more_{user_id}_{len(messages)}"
                    )
                ],
                [
                    InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
                ]
            ])
            await target.answer(chat_text, reply_markup=keyboard, parse_mode="HTML")
            chat_text = header  # Сбрасываем для следующей части
    
    # Отправляем последнюю часть
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin_chat_user_{user_id}"),
            InlineKeyboardButton(text="🗑️ Удалить всё", callback_data=f"admin_chat_clear_{user_id}")
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"admin_ban_user_{user_id}"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin_unban_user_{user_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    await target.answer(chat_text, reply_markup=keyboard, parse_mode="HTML")


# ✅ ПОКАЗАТЬ ЕЩЁ СООБЩЕНИЯ
@router.callback_query(lambda c: c.data.startswith("admin_chat_more_"))
async def admin_chat_more(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    
    # Показываем следующие 30 сообщений
    async with async_session() as session:
        messages = await session.scalars(
            select(SavedMessage)
            .where(SavedMessage.user_id == user_id)
            .order_by(SavedMessage.saved_at.desc())
            .offset(30)
            .limit(30)
        )
        messages = list(messages)
    
    if not messages:
        await callback.answer("📭 Больше сообщений нет", show_alert=True)
        return
    
    chat_text = ""
    for msg in reversed(messages):
        time_str = msg.saved_at.strftime('%H:%M')
        name = msg.from_username or msg.from_first_name or 'Аноним'
        
        if msg.from_user_id == user_id:
            chat_text += f"\n👤 <b>{name}</b> [{time_str}]:\n"
        else:
            chat_text += f"\n🤖 <b>{name}</b> [{time_str}]:\n"
        
        if msg.text:
            text_preview = msg.text[:500]
            if len(msg.text) > 500:
                text_preview += "..."
            chat_text += f"{text_preview}\n"
        
        if msg.media_type:
            chat_text += f"🖼️ <i>[{msg.media_type}]</i>\n"
        
        chat_text += "➖➖➖➖➖➖➖➖➖➖\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📥 Ещё",
                callback_data=f"admin_chat_more_{user_id}_{int(callback.data.split('_')[-1]) + 30}"
            )
        ],
        [
            InlineKeyboardButton(text="🔙 Назад к чату", callback_data=f"admin_chat_user_{user_id}")
        ]
    ])
    
    await callback.message.answer(chat_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ ОЧИСТКА ВСЕХ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ
@router.callback_query(lambda c: c.data.startswith("admin_chat_clear_"))
async def admin_chat_clear(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить всё", callback_data=f"admin_chat_clear_confirm_{user_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_chat_user_{user_id}")
        ]
    ])
    
    await callback.message.edit_text(
        f"⚠️ <b>Удалить все сообщения пользователя {user_id}?</b>\n\n"
        f"Это действие необратимо!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("admin_chat_clear_confirm_"))
async def admin_chat_clear_confirm(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        # Удаляем все сообщения пользователя
        messages = await session.scalars(
            select(SavedMessage).where(SavedMessage.user_id == user_id)
        )
        
        deleted_count = 0
        for msg in messages:
            # Удаляем медиа-файлы
            if msg.media_path and os.path.exists(msg.media_path):
                try:
                    os.remove(msg.media_path)
                except:
                    pass
            await session.delete(msg)
            deleted_count += 1
        
        await session.commit()
    
    await callback.message.edit_text(
        f"✅ Удалено {deleted_count} сообщений пользователя {user_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
        parse_mode="HTML"
    )
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
    
    await show_chat_interface(callback.message, user_id)


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
    
    await show_chat_interface(callback.message, user_id)


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