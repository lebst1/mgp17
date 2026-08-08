from aiogram import Router, Bot, F
import shutil
import time
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile, BufferedInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository
from src.db.repositories.business_repository import BusinessRepository
from src.db.repositories.payment_repository import PaymentRepository
from src.db.session import async_session, cleanup_old_data
from src.config import settings
from sqlalchemy import select, func, or_, and_, desc, case
from sqlalchemy.orm import selectinload
from src.db.models import User, SavedMessage, BusinessConnection, Payment, ReferralBonus
import os
import logging
from datetime import datetime, timedelta
import pytz
from src.db.models import User, SavedMessage, BusinessConnection, Payment, ReferralBonus, PaymentProvider, OrderStatus
from sqlalchemy import select, func, or_, and_, desc, case, text

logger = logging.getLogger(__name__)

router = Router()

MAX_MEDIA_FILES = 50
MAX_MEDIA_AGE_DAYS = 1
CHATS_PER_PAGE = 10
MESSAGES_PER_PAGE = 15
USERS_PER_PAGE = 15


# ✅ УСТАНАВЛИВАЕМ МОСКОВСКОЕ ВРЕМЯ
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


def format_datetime(dt):
    """Форматирует время по Москве"""
    if dt is None:
        return "Неизвестно"
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    moscow_time = dt.astimezone(MOSCOW_TZ)
    return moscow_time.strftime('%d.%m.%Y %H:%M:%S')


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
    waiting_for_chat_page = State()
    waiting_for_sub_info = State()
    waiting_for_sub_add = State()
    waiting_for_sub_remove = State()
    waiting_for_sub_grant_user = State()
    waiting_for_sub_revoke_user = State()
    waiting_for_user_search = State()


# ✅ ПРОВЕРКА АДМИНА (только владелец)
async def is_admin(user_id: int) -> bool:
    return user_id == settings.OWNER_TELEGRAM_ID


# ✅ БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ СООБЩЕНИЯ
async def safe_edit_message(message, text, reply_markup=None, parse_mode="HTML"):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except Exception as e:
        if "message is not modified" in str(e):
            return False
        raise e


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
🗄️ <b>Очистка диска</b> — удалить старые медиа-файлы
💾 <b>Бэкап</b> — создать бэкап
💚 <b>Статус</b> — состояние бота

➕ <b>Выдать подписку</b> — продлить доступ
➖ <b>Забрать подписку</b> — отозвать доступ
📋 <b>Подписки</b> — список подписок
🎁 <b>Рефералы</b> — статистика рефералов
💳 <b>Платежи</b> — история платежей
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")
        ],
        [
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
            InlineKeyboardButton(text="🗄️ Очистка диска", callback_data="admin_cleanup_disk")  # 👈 НОВАЯ КНОПКА
        ],
        [
            InlineKeyboardButton(text="➕ Выдать подписку", callback_data="admin_sub_grant"),
            InlineKeyboardButton(text="➖ Забрать подписку", callback_data="admin_sub_revoke")
        ],
        [
            InlineKeyboardButton(text="📋 Подписки", callback_data="admin_subscriptions"),
            InlineKeyboardButton(text="🎁 Рефералы", callback_data="admin_referrals")
        ],
        [
            InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments")
        ],
        [
            InlineKeyboardButton(text="💾 Бэкап", callback_data="admin_backup"),
            InlineKeyboardButton(text="💚 Статус", callback_data="admin_status")
        ]
    ])
    
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await safe_edit_message(target.message, text, keyboard)


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
    
    await safe_edit_message(callback.message, "📊 <b>Загрузка статистики...</b>", parse_mode="HTML")
    
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

    sub_stats = await UserRepository.get_subscription_stats()
    pay_stats = await PaymentRepository.get_stats()
    
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

━━━━━━━━━━━━━━━━━━━━━
👤 <b>Пользователи:</b> {users_count or 0}
📝 <b>Всего сообщений:</b> {messages_count or 0}
🗑️ <b>Удалено:</b> {deleted_count or 0}
✏️ <b>Отредактировано:</b> {edited_count or 0}
🖼️ <b>Медиа в БД:</b> {media_count or 0}
💾 <b>Медиа на диске:</b> {media_files} ({media_dir_size / 1024 / 1024:.1f} МБ)
🔗 <b>Бизнес-подключений:</b> {connections_count or 0}
━━━━━━━━━━━━━━━━━━━━━

<b>Подписки:</b>
👤 Всего пользователей: {sub_stats.get('total_users', 0)}
✅ Активных подписок: {sub_stats.get('active_subscriptions', 0)}
❌ Истекших подписок: {sub_stats.get('expired_subscriptions', 0)}
🎁 Всего рефералов: {sub_stats.get('total_referrals', 0)}

<b>Платежи:</b>
💳 Всего платежей: {pay_stats.get('total_payments', 0)}
✅ Успешных: {pay_stats.get('paid_payments', 0)}
💰 Сумма: {pay_stats.get('total_amount', 0):.0f}₽
━━━━━━━━━━━━━━━━━━━━━

🔄 <i>Обновлено: {format_datetime(datetime.now())}</i>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
        ]
    ])
    
    await safe_edit_message(callback.message, text, keyboard)
    await callback.answer()


# ✅ РАССЫЛКА
@router.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await safe_edit_message(
        callback.message,
        "📨 <b>Рассылка</b>\n\n"
        "Отправь сообщение, которое нужно разослать всем пользователям.\n"
        "Это может быть текст, фото, видео.\n\n"
        "⚠️ <i>Сообщение будет отправлено ВСЕМ пользователям!</i>\n\n"
        "Отправь /cancel чтобы отменить.",
        InlineKeyboardMarkup(inline_keyboard=[
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
    
    status_msg = await message.answer("⏳ <b>Начинаю рассылку...</b>", parse_mode="HTML")
    
    async with async_session() as session:
        users = await session.scalars(select(User))
    
    count = 0
    failed = 0
    
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
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user.telegram_id}: {e}")
    
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 <b>Отправлено:</b> {count}\n"
        f"❌ <b>Ошибок:</b> {failed}",
        parse_mode="HTML"
    )
    await state.clear()


# ✅ ПОИСК ПОЛЬЗОВАТЕЛЯ
@router.callback_query(lambda c: c.data == "admin_search")
async def admin_search(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await safe_edit_message(
        callback.message,
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Отправь ID пользователя или его @username для поиска.\n\n"
        "📌 <b>Примеры:</b>\n"
        "• <code>123456789</code> — по ID\n"
        "• <code>@username</code> — по юзернейму\n\n"
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
    
    user_info = f"{user.first_name or 'Не указано'}"
    if user.username:
        user_info += f" (@{user.username})"
    
    text = f"""
👤 <b>Найден пользователь</b>

━━━━━━━━━━━━━━━━━━━━━
🆔 ID: <code>{user.telegram_id}</code>
👤 Имя: {user_info}
📛 Юзернейм: @{user.username or 'Нет'}
✅ Активен: {'✅ Да' if user.is_active else '❌ Нет'}
📝 Сообщений: {messages_count or 0}
🗑️ Удалено: {deleted_count or 0}
✏️ Отредактировано: {edited_count or 0}
💬 Чатов: {len(chats)}
📅 Зарегистрирован: {format_datetime(user.created_at)}
━━━━━━━━━━━━━━━━━━━━━
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
            InlineKeyboardButton(text="📋 Меню пользователя", callback_data=f"admin_user_menu_{user.telegram_id}")
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
    await show_chats_list(callback.message, user_id, 1)
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_chats")
async def admin_chats(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await safe_edit_message(
        callback.message,
        "💬 <b>Чаты пользователя</b>\n\n"
        "Отправь ID пользователя, чтобы увидеть список его чатов.\n\n"
        "📌 <b>Пример:</b> <code>123456789</code>\n\n"
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
    
    try:
        user_id = int(message.text.strip())
        await show_chats_list(message, user_id, 1)
    except ValueError:
        await message.answer("❌ Неверный формат. Отправь ID пользователя.")
    
    await state.clear()


@router.callback_query(lambda c: c.data.startswith("admin_chats_page_"))
async def admin_chats_page(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    page = int(parts[4])
    
    await show_chats_list(callback.message, user_id, page)
    await callback.answer()


async def show_chats_list(target, user_id: int, page: int = 1):
    CHATS_PER_PAGE = 10
    
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await target.answer("❌ Пользователь не найден")
            return
        
        # Считаем общее количество чатов (без фильтра)
        total_chats_result = await session.execute(
            text("""
                SELECT COUNT(DISTINCT chat_id) 
                FROM saved_messages 
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        )
        total_chats = total_chats_result.scalar() or 0
        total_pages = (total_chats + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE if total_chats > 0 else 1
        
        offset = (page - 1) * CHATS_PER_PAGE
        
        # Получаем ВСЕ чаты (без фильтра по отправителю)
        chats_query = text("""
            SELECT 
                sm.chat_id,
                MAX(sm.chat_title) as chat_title,
                MAX(sm.from_username) as from_username,
                MAX(sm.from_first_name) as from_first_name,
                COUNT(sm.id) as count,
                MAX(sm.saved_at) as last_activity,
                SUM(CASE WHEN sm.is_deleted = 1 THEN 1 ELSE 0 END) as deleted_count,
                SUM(CASE WHEN sm.is_edited = 1 THEN 1 ELSE 0 END) as edited_count
            FROM saved_messages sm
            WHERE sm.user_id = :user_id
            GROUP BY sm.chat_id
            ORDER BY last_activity DESC
            LIMIT :limit OFFSET :offset
        """)
        
        chats = await session.execute(
            chats_query,
            {
                "user_id": user_id,
                "limit": CHATS_PER_PAGE,
                "offset": offset
            }
        )
        chats = chats.all()
    
    if not chats:
        await target.answer("📭 Нет сохранённых чатов у этого пользователя.")
        return
    
    # Формируем информацию о пользователе
    user_info = f"{user.first_name or user.username or 'Пользователь'}"
    if user.username:
        user_info += f" (@{user.username})"
    
    result_text = f"""
📋 <b>Чаты пользователя</b>
{user_info}
🆔 <code>{user.telegram_id}</code>
📊 <b>Всего чатов:</b> {total_chats}
📄 <b>Страница {page} из {total_pages}</b>

➖➖➖➖➖➖➖➖➖➖➖➖
"""
    
    keyboard_buttons = []
    now = datetime.now()
    
    for i, chat in enumerate(chats, 1):
        chat_title = chat.chat_title or f"Чат {chat.chat_id}"
        
        # Определяем имя собеседника
        contact_name = ""
        if chat.from_first_name:
            contact_name = chat.from_first_name
        if chat.from_username:
            if contact_name:
                contact_name += f" (@{chat.from_username})"
            else:
                contact_name = f"@{chat.from_username}"
        
        if not contact_name:
            contact_name = "Неизвестный"
        
        display_name = chat_title[:15] + "..." if len(chat_title) > 15 else chat_title
        
        status = ""
        if chat.deleted_count and chat.deleted_count > 0:
            status += f"🗑️{chat.deleted_count} "
        if chat.edited_count and chat.edited_count > 0:
            status += f"✏️{chat.edited_count} "
        
        last_active = ""
        if chat.last_activity:
            try:
                if isinstance(chat.last_activity, str):
                    from datetime import datetime as dt
                    last_activity_dt = dt.fromisoformat(chat.last_activity.replace('Z', '+00:00'))
                else:
                    last_activity_dt = chat.last_activity
                
                diff = now - last_activity_dt
                if diff.days > 0:
                    last_active = f" {diff.days}д"
                elif diff.seconds > 3600:
                    last_active = f" {diff.seconds//3600}ч"
                elif diff.seconds > 60:
                    last_active = f" {diff.seconds//60}м"
                else:
                    last_active = " 🔴"
            except Exception:
                last_active = ""
        
        # Кнопка
        button_text = f"#{i + offset} {contact_name} | {display_name} ({chat.count}) {status}{last_active}".strip()
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text[:60],
                callback_data=f"admin_chat_open_{user_id}_{chat.chat_id}"
            )
        ])
    
    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_chats_page_{user_id}_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="➡️ Вперед", callback_data=f"admin_chats_page_{user_id}_{page+1}")
        )
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await target.answer(result_text, reply_markup=keyboard, parse_mode="HTML")

# ✅ ОТКРЫТЬ КОНКРЕТНЫЙ ЧАТ
@router.callback_query(lambda c: c.data.startswith("admin_chat_open_"))
async def admin_chat_open(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    
    await show_chat_messages(callback.message, user_id, chat_id, None, 1)
    await callback.answer()


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
    
    await show_chat_messages(callback.message, user_id, chat_id, filter_type, 1)
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
            .limit(30)
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
            caption = f"📎 <b>{msg.media_type}</b>\n🕐 {format_datetime(msg.saved_at)}"
            
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
            elif msg.media_type == "video_note":
                await callback.message.answer_video_note(video_note=media_file)
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
        time_str = format_datetime(msg.saved_at)
        name = msg.from_username or msg.from_first_name or 'Аноним'
        
        if msg.from_username:
            name = f"{name} (@{msg.from_username})"
        
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


@router.callback_query(lambda c: c.data.startswith("admin_chat_page_"))
async def admin_chat_page(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[3])
    chat_id = int(parts[4])
    page = int(parts[5])
    filter_type = parts[6] if len(parts) > 6 else "all"
    
    if filter_type == "all":
        filter_type = None
    
    await show_chat_messages(callback.message, user_id, chat_id, filter_type, page)
    await callback.answer()


async def show_chat_messages(target, user_id: int, chat_id: int, filter_type: str = None, page: int = 1):
    MESSAGES_PER_PAGE = 15
    
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
        
        total_count = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        total_pages = (total_count + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE if total_count else 1
        
        offset = (page - 1) * MESSAGES_PER_PAGE
        
        messages = await session.scalars(
            stmt.order_by(SavedMessage.saved_at.desc())
            .offset(offset)
            .limit(MESSAGES_PER_PAGE)
        )
        messages = list(messages)
    
    if not messages:
        await target.answer("📭 Нет сообщений в этом чате")
        return
    
    chat_title_display = chat_title or f"Чат {chat_id}"
    
    filter_text = ""
    if filter_type == "deleted":
        filter_text = " 🗑️ (только удаленные)"
    elif filter_type == "edited":
        filter_text = " ✏️ (только правки)"
    elif filter_type == "media":
        filter_text = " 🖼️ (только медиа)"
    
    user_info = f"{user.first_name or user.username or 'Пользователь'}"
    if user.username:
        user_info += f" (@{user.username})"
    
    header = f"""
💬 <b>Чат: {chat_title_display}</b>{filter_text}

👤 <b>{user_info}</b>
🆔 <code>{user.telegram_id}</code>
💬 ID чата: <code>{chat_id}</code>
📊 <b>Показано:</b> {len(messages)} из {total_count}
📄 <b>Страница {page} из {total_pages}</b>

➖➖➖➖➖➖➖➖➖➖➖➖
"""
    
    chat_text = header
    media_items = []
    
    for msg in reversed(messages):
        time_str = format_datetime(msg.saved_at)
        name = msg.from_username or msg.from_first_name or 'Аноним'
        
        if msg.from_username:
            name = f"{name} (@{msg.from_username})"
        
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
                "sticker": "🎨",
                "video_note": "🎥"
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
    
    if media_items:
        await target.answer("🖼️ <b>Медиа в этом чате:</b>", parse_mode="HTML")
        for msg in media_items[:10]:
            try:
                media_file = FSInputFile(msg.media_path)
                caption = f"📎 <b>{msg.media_type}</b>\n🕐 {format_datetime(msg.saved_at)}"
                
                if msg.text:
                    caption += f"\n📝 {msg.text[:100]}{'...' if len(msg.text) > 100 else ''}"
                
                if msg.media_type == "photo":
                    await target.answer_photo(photo=media_file, caption=caption, parse_mode="HTML")
                elif msg.media_type == "video":
                    await target.answer_video(video=media_file, caption=caption, parse_mode="HTML")
                elif msg.media_type == "video_note":
                    await target.answer_video_note(video_note=media_file)
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
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"admin_chat_page_{user_id}_{chat_id}_{page-1}_{filter_type or 'all'}"
            )
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️ Вперед",
                callback_data=f"admin_chat_page_{user_id}_{chat_id}_{page+1}_{filter_type or 'all'}"
            )
        )
    
    keyboard_buttons = [
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin_chat_open_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="🗑️ Удалить чат", callback_data=f"admin_chat_delete_{user_id}_{chat_id}")
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
        ]
    ]
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="💬 Список чатов", callback_data=f"admin_chats_user_{user_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
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
    
    await safe_edit_message(
        callback.message,
        f"⚠️ <b>Удалить весь чат?</b>\n\n"
        f"Пользователь: {user_id}\n"
        f"Чат: {chat_id}\n\n"
        f"Это действие необратимо!",
        keyboard
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
    
    await safe_edit_message(
        callback.message,
        f"✅ Удалено {deleted_count} сообщений из чата {chat_id}",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Список чатов", callback_data=f"admin_chats_user_{user_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
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
    
    await safe_edit_message(
        callback.message,
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
    
    await safe_edit_message(
        callback.message,
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


# ✅ НОВЫЙ СПИСОК ПОЛЬЗОВАТЕЛЕЙ С ПАГИНАЦИЕЙ И КНОПКАМИ

@router.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    """Список пользователей с пагинацией и кнопками перехода в чат."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await show_users_list(callback.message, 1)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("admin_users_page_"))
async def admin_users_page(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    page = int(callback.data.split("_")[-1])
    await show_users_list(callback.message, page)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("admin_user_chat_"))
async def admin_user_chat(callback: CallbackQuery):
    """Переход в чат пользователя по клику."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    await show_chats_list(callback.message, user_id, 1)
    await callback.answer()


# ✅ МЕНЮ ПОЛЬЗОВАТЕЛЯ
@router.callback_query(F.data.startswith("admin_user_menu_"))
async def admin_user_menu(callback: CallbackQuery):
    """Меню управления пользователем."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        user = await session.scalar(
            select(User)
            .where(User.telegram_id == user_id)
            .options(selectinload(User.direct_referrals))
        )
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        sub_status = "✅ Активна" if user.has_active_subscription() else "❌ Истекла"
        sub_until = user.subscription_until.strftime("%d.%m.%Y") if user.subscription_until else "—"
        status_icon = "🟢 Активен" if user.is_active else "🔴 Заблокирован"
        referrals_count = len(user.direct_referrals) if user.direct_referrals else 0
        
        text = f"""
📋 <b>Меню пользователя</b>

━━━━━━━━━━━━━━━━━━━━━
🆔 ID: <code>{user.telegram_id}</code>
👤 Имя: {user.first_name or 'Не указано'}
📛 Юзернейм: @{user.username or 'Нет'}
✅ Статус: {status_icon}
💳 Подписка: {sub_status} (до {sub_until})
📊 Сообщений: {user.messages_saved or 0}
🎁 Рефералов: {referrals_count}
📅 Зарегистрирован: {format_datetime(user.created_at)}
━━━━━━━━━━━━━━━━━━━━━

Выберите действие:
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Чаты", callback_data=f"admin_chats_user_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"admin_ban_user_{user_id}"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin_unban_user_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="➕ Выдать подписку", callback_data=f"admin_user_grant_sub_{user_id}"),
            InlineKeyboardButton(text="➖ Забрать подписку", callback_data=f"admin_user_revoke_sub_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑️ Удалить из БД", callback_data=f"admin_user_delete_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_users"),
        ]
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ✅ ВЫДАТЬ ПОДПИСКУ ИЗ МЕНЮ
@router.callback_query(F.data.startswith("admin_user_grant_sub_"))
async def admin_user_grant_sub(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    await state.update_data(grant_user_id=user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 день", callback_data="admin_grant_days_1"),
            InlineKeyboardButton(text="7 дней", callback_data="admin_grant_days_7"),
        ],
        [
            InlineKeyboardButton(text="30 дней", callback_data="admin_grant_days_30"),
            InlineKeyboardButton(text="90 дней", callback_data="admin_grant_days_90"),
        ],
        [
            InlineKeyboardButton(text="365 дней", callback_data="admin_grant_days_365"),
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_user_menu_{user_id}")],
    ])
    
    await safe_edit_message(
        callback.message,
        f"👤 Пользователь: <code>{user_id}</code>\n\nВыбери срок подписки:",
        keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# ✅ ЗАБРАТЬ ПОДПИСКУ ИЗ МЕНЮ
@router.callback_query(F.data.startswith("admin_user_revoke_sub_"))
async def admin_user_revoke_sub(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    user = await UserRepository.revoke_subscription(user_id)
    
    if user:
        await callback.answer(f"✅ Подписка пользователя {user_id} отозвана!", show_alert=True)
        await admin_user_menu(callback)
    else:
        await callback.answer(f"❌ Пользователь {user_id} не найден!", show_alert=True)


# ✅ УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ (НОВОЕ)
@router.callback_query(F.data.startswith("admin_user_delete_"))
async def admin_user_delete(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    logger.info(f"🔍 admin_user_delete: {callback.data}")  # 👈 ЛОГ
    
    user_id = int(callback.data.split("_")[-1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить навсегда", callback_data=f"delete_user_{user_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_user_menu_{user_id}"),
        ]
    ])
    
    text = f"""
⚠️ <b>ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ</b>

Вы действительно хотите удалить пользователя?

👤 ID: <code>{user_id}</code>

<b>Будут удалены:</b>
• Все сообщения пользователя
• Все медиа-файлы
• Настройки SAVE MODE
• Реферальные бонусы
• Бизнес-подключения

<b>Это действие НЕОБРАТИМО!</b>
"""
    
    await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer("⚠️ Подтвердите удаление")


# ✅ ФИНАЛЬНОЕ УДАЛЕНИЕ
@router.callback_query(F.data.startswith("delete_user_"))
async def delete_user(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    user_id = int(callback.data.split("_")[-1])
    await callback.answer("⏳ Удаление...", show_alert=False)

    try:
        async with async_session() as session:
            # 1. Удаляем сообщения и медиа
            messages = await session.scalars(
                select(SavedMessage).where(SavedMessage.user_id == user_id)
            )
            deleted_messages = 0
            for msg in messages:
                if msg.media_path and os.path.exists(msg.media_path):
                    try:
                        os.remove(msg.media_path)
                    except Exception:
                        pass
                await session.delete(msg)
                deleted_messages += 1

            # 2. Удаляем реферальные бонусы
            bonuses = await session.scalars(
                select(ReferralBonus).where(
                    or_(
                        ReferralBonus.referrer_id == user_id,
                        ReferralBonus.referred_id == user_id
                    )
                )
            )
            for bonus in bonuses:
                await session.delete(bonus)

            # 3. Удаляем бизнес-подключения
            connections = await session.scalars(
                select(BusinessConnection).where(BusinessConnection.user_id == user_id)
            )
            for conn in connections:
                await session.delete(conn)

            # 4. Удаляем самого пользователя
            user = await session.scalar(
                select(User).where(User.telegram_id == user_id)
            )
            if user:
                await session.delete(user)

            await session.commit()

        # ✅ Сообщение об успехе
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_users")]
        ])

        await callback.message.edit_text(
            f"✅ Пользователь <code>{user_id}</code> ПОЛНОСТЬЮ УДАЛЕН!\n\n"
            f"Удалено сообщений: {deleted_messages}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer("✅ Пользователь удален!", show_alert=True)

    except Exception as e:
        logger.error(f"❌ Ошибка удаления пользователя {user_id}: {e}")
        # Обрезаем сообщение об ошибке, чтобы не превысить лимит Telegram
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."

        await callback.message.answer(
            f"❌ Ошибка при удалении: {error_msg}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]
            ])
        )
        await callback.answer("❌ Ошибка при удалении", show_alert=True)

async def show_users_list(target, page: int = 1, search_query: str = None):
    """Отображает список пользователей с пагинацией и кнопками."""
    USERS_PER_PAGE = 15
    
    async with async_session() as session:
        stmt = select(User)
        if search_query:
            stmt = stmt.where(
                or_(
                    User.telegram_id.ilike(f"%{search_query}%"),
                    User.username.ilike(f"%{search_query}%"),
                    User.first_name.ilike(f"%{search_query}%"),
                )
            )
        
        total_users = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        total_pages = (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE if total_users > 0 else 1
        
        offset = (page - 1) * USERS_PER_PAGE
        users = await session.scalars(
            stmt.order_by(User.created_at.desc()).offset(offset).limit(USERS_PER_PAGE)
        )
        users = list(users)
    
    if not users:
        text = "📋 <b>Пользователи</b>\n\nПользователей пока нет."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
        await safe_edit_message(target, text, keyboard)
        return
    
    text = f"📋 <b>Список пользователей</b> (стр. {page}/{total_pages}, всего: {total_users})\n\n"
    keyboard_buttons = []
    
    for user in users:
        sub_status = "✅" if user.has_active_subscription() else "❌"
        sub_until = user.subscription_until.strftime("%d.%m") if user.subscription_until else "—"
        name = user.first_name or user.username or str(user.telegram_id)
        if len(name) > 20:
            name = name[:17] + "..."
        status_icon = "🟢" if user.is_active else "🔴"
        msg_count = user.messages_saved or 0
        
        user_line = f"{status_icon} <code>{user.telegram_id}</code>"
        if user.username:
            user_line += f" <b>@{user.username}</b>"
        user_line += f" {name} | {sub_status} {sub_until} | 📊{msg_count}"
        text += user_line + "\n"
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"📋 {name[:12]}",
                callback_data=f"admin_user_menu_{user.telegram_id}"
            )
        ])
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="admin_users_current"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_users_page_{page+1}"))
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔍 Поиск", callback_data="admin_users_search"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await safe_edit_message(target, text, keyboard)


@router.callback_query(lambda c: c.data == "admin_users_search")
async def admin_users_search(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await safe_edit_message(
        callback.message,
        "🔍 <b>Поиск пользователей</b>\n\n"
        "Введите ID, username или имя для поиска.\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_search)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_search)
async def process_user_search(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    query = message.text.strip()
    if query.lower() == "/cancel":
        await state.clear()
        await show_admin_panel(message)
        return
    
    await show_users_list(message, 1, query)
    await state.clear()


# ✅ ОЧИСТКА СТАРЫХ МЕДИА
async def cleanup_old_media():
    try:
        async with async_session() as session:
            cutoff_date = datetime.now() - timedelta(days=MAX_MEDIA_AGE_DAYS)
            
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
    
    await safe_edit_message(callback.message, "🧹 <b>Очистка БД...</b>", parse_mode="HTML")
    
    try:
        await cleanup_old_data()
        await cleanup_old_media()
        await safe_edit_message(
            callback.message,
            "✅ Очистка БД и медиа завершена!",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )
    except Exception as e:
        await safe_edit_message(callback.message, f"❌ Ошибка очистки: {e}", parse_mode="HTML")
    
    await callback.answer()

@router.callback_query(lambda c: c.data == "admin_cleanup_disk")
async def admin_cleanup_disk(callback: CallbackQuery):
    """Очистка диска от старых медиа-файлов"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await safe_edit_message(callback.message, "🗄️ <b>Очистка диска...</b>", parse_mode="HTML")
    await callback.answer()
    
    try:
        # 1. Собираем статистику перед очисткой
        media_dir = settings.MEDIA_DIR
        total_size_before = 0
        total_files_before = 0
        
        if os.path.exists(media_dir):
            for f in os.listdir(media_dir):
                f_path = os.path.join(media_dir, f)
                if os.path.isfile(f_path):
                    total_size_before += os.path.getsize(f_path)
                    total_files_before += 1
        
        # 2. Получаем список файлов, которые есть в БД
        async with async_session() as session:
            db_files = await session.scalars(
                select(SavedMessage.media_path).where(SavedMessage.media_path.isnot(None))
            )
            db_files_set = {f for f in db_files if f}
        
        # 3. Удаляем файлы, которых нет в БД (осиротевшие)
        removed_count = 0
        removed_size = 0
        
        if os.path.exists(media_dir):
            for filename in os.listdir(media_dir):
                file_path = os.path.join(media_dir, filename)
                if os.path.isfile(file_path):
                    # Проверяем, есть ли файл в БД
                    if file_path not in db_files_set:
                        try:
                            removed_size += os.path.getsize(file_path)
                            os.remove(file_path)
                            removed_count += 1
                        except Exception as e:
                            logger.error(f"❌ Не удалось удалить {file_path}: {e}")
        
        # 4. Считаем статистику после очистки
        total_size_after = 0
        total_files_after = 0
        
        if os.path.exists(media_dir):
            for f in os.listdir(media_dir):
                f_path = os.path.join(media_dir, f)
                if os.path.isfile(f_path):
                    total_size_after += os.path.getsize(f_path)
                    total_files_after += 1
        
        # 5. Формируем отчет
        size_before_mb = total_size_before / 1024 / 1024
        size_after_mb = total_size_after / 1024 / 1024
        freed_mb = removed_size / 1024 / 1024
        
        text = f"""
🗄️ <b>Очистка диска завершена!</b>

📊 <b>Статистика:</b>
• Файлов до: <b>{total_files_before}</b>
• Файлов после: <b>{total_files_after}</b>
• Удалено файлов: <b>{removed_count}</b>

💾 <b>Освобождено места:</b> <b>{freed_mb:.2f} МБ</b>
📁 <b>Размер папки до:</b> {size_before_mb:.2f} МБ
📁 <b>Размер папки после:</b> {size_after_mb:.2f} МБ

✅ <i>Удалены только файлы, которых нет в базе данных.</i>
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_cleanup_disk")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
        
        await safe_edit_message(callback.message, text, keyboard)
        
    except Exception as e:
        logger.error(f"❌ Ошибка очистки диска: {e}")
        await safe_edit_message(
            callback.message,
            f"❌ Ошибка очистки диска: {str(e)[:200]}",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )


# ✅ БЭКАП
@router.callback_query(lambda c: c.data == "admin_backup")
async def admin_backup(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        date = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if os.path.exists("data/app.db"):
            shutil.copy2("data/app.db", f"{backup_dir}/app_{date}.db")
            await safe_edit_message(
                callback.message,
                f"✅ Бэкап создан: app_{date}.db",
                InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
                ])
            )
        else:
            await safe_edit_message(callback.message, "❌ Файл БД не найден!", parse_mode="HTML")
    except Exception as e:
        await safe_edit_message(callback.message, f"❌ Ошибка бэкапа: {e}", parse_mode="HTML")
    
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    
    await safe_edit_message(callback.message, text, keyboard)
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


# ✅ ВЫДАТЬ ПОДПИСКУ
@router.callback_query(lambda c: c.data == "admin_sub_grant")
async def admin_sub_grant(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await safe_edit_message(
        callback.message,
        "➕ <b>Выдать подписку</b>\n\nОтправь Telegram ID пользователя:",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_back")]
        ]),
    )
    await state.set_state(AdminStates.waiting_for_sub_grant_user)
    await callback.answer()


@router.message(AdminStates.waiting_for_sub_grant_user)
async def admin_sub_grant_user(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Отправь числовой Telegram ID.")
        return

    user = await UserRepository.get_by_id(user_id)
    if not user:
        await message.answer(f"❌ Пользователь {user_id} не найден.")
        await state.clear()
        return

    await state.update_data(grant_user_id=user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 день", callback_data="admin_grant_days_1"),
            InlineKeyboardButton(text="7 дней", callback_data="admin_grant_days_7"),
        ],
        [
            InlineKeyboardButton(text="30 дней", callback_data="admin_grant_days_30"),
            InlineKeyboardButton(text="90 дней", callback_data="admin_grant_days_90"),
        ],
        [
            InlineKeyboardButton(text="365 дней", callback_data="admin_grant_days_365"),
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_back")],
    ])
    await message.answer(
        f"👤 Пользователь: <code>{user_id}</code>\n\nВыбери срок подписки:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith("admin_grant_days_"))
async def admin_grant_days(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    days = int(callback.data.split("_")[-1])
    data = await state.get_data()
    user_id = data.get("grant_user_id")
    if not user_id:
        await callback.answer("❌ ID не найден", show_alert=True)
        return

    user = await UserRepository.extend_subscription(user_id, days)
    until = format_datetime(user.subscription_until) if user else "—"
    
    # ✅ УВЕДОМЛЕНИЕ ПОЛЬЗОВАТЕЛЮ
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=f"🎉 <b>Подписка активирована!</b>\n\n"
                 f"Вам выдана подписка на <b>{days} дней</b>.\n"
                 f"Действует до: <b>{until}</b>\n\n"
                 f"Теперь вам доступны все функции бота! 🚀",
            parse_mode="HTML"
        )
        logger.info(f"✅ Уведомление о подписке отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Не удалось отправить уведомление {user_id}: {e}")
    
    await safe_edit_message(
        callback.message,
        f"✅ Подписка выдана!\n\n👤 ID: <code>{user_id}</code>\n📅 До: {until}\n➕ Дней: {days}\n📨 Уведомление отправлено!",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
    )
    await state.clear()
    await callback.answer()


# ✅ ЗАБРАТЬ ПОДПИСКУ
@router.callback_query(lambda c: c.data == "admin_sub_revoke")
async def admin_sub_revoke(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await safe_edit_message(
        callback.message,
        "➖ <b>Забрать подписку</b>\n\nОтправь Telegram ID пользователя:",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_back")]
        ]),
    )
    await state.set_state(AdminStates.waiting_for_sub_revoke_user)
    await callback.answer()


@router.message(AdminStates.waiting_for_sub_revoke_user)
async def admin_sub_revoke_user(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Отправь числовой Telegram ID.")
        return

    user = await UserRepository.revoke_subscription(user_id)
    if user:
        await message.answer(f"✅ Подписка пользователя <code>{user_id}</code> отозвана.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Пользователь {user_id} не найден.")
    await state.clear()


# ✅ СПИСОК ПОДПИСОК
@router.callback_query(lambda c: c.data == "admin_subscriptions")
async def admin_subscriptions(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    now = datetime.utcnow()
    async with async_session() as session:
        active = await session.scalars(
            select(User).where(User.subscription_until > now).order_by(User.subscription_until.desc()).limit(15)
        )
        active = list(active)

    text = "📋 <b>Активные подписки (15):</b>\n\n"
    if not active:
        text += "Нет активных подписок."
    else:
        for u in active:
            until = format_datetime(u.subscription_until)
            name = u.first_name or u.username or str(u.telegram_id)
            username_str = f" (@{u.username})" if u.username else ""
            text += f"👤 <code>{u.telegram_id}</code> {name}{username_str} | до {until}\n"

    await safe_edit_message(
        callback.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
    )
    await callback.answer()


# ✅ РЕФЕРАЛЫ
@router.callback_query(lambda c: c.data == "admin_referrals")
async def admin_referrals(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    stats = await UserRepository.get_subscription_stats()
    async with async_session() as session:
        top = await session.scalars(
            select(User).where(User.referrals_count > 0).order_by(User.referrals_count.desc()).limit(10)
        )
        top = list(top)

    text = f"""
🎁 <b>Реферальная статистика</b>

👥 Всего рефералов: {stats.get('total_referrals', 0)}

<b>Топ рефереров:</b>
"""
    if not top:
        text += "Пока нет рефералов."
    else:
        for u in top:
            name = u.first_name or u.username or str(u.telegram_id)
            username_str = f" (@{u.username})" if u.username else ""
            text += f"👤 <code>{u.telegram_id}</code> {name}{username_str} — {u.referrals_count} реф., {u.referral_days_earned} дн.\n"

    await safe_edit_message(
        callback.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
    )
    await callback.answer()


# ✅ ПЛАТЕЖИ
@router.callback_query(lambda c: c.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    try:
        async with async_session() as session:
            # Получаем все платежи из таблицы payments
            payments = await session.scalars(
                select(Payment).order_by(Payment.created_at.desc()).limit(50)
            )
            payments = list(payments)
            
            # Статистика
            total = len(payments)
            paid = sum(1 for p in payments if p.status == OrderStatus.PAID)
            total_amount = sum(float(p.amount) for p in payments if p.status == OrderStatus.PAID)
            
            text = f"""
💳 <b>Платежи</b>

Всего: {total}
✅ Успешных: {paid}
💰 Сумма: {total_amount:.0f} {"⭐" if any(p.provider == PaymentProvider.STARS for p in payments) else "₽"}

<b>Последние платежи:</b>
"""
            
            if not payments:
                text += "Платежей пока нет."
            else:
                for p in payments[:15]:
                    # Определяем валюту
                    currency = "⭐" if p.provider == PaymentProvider.STARS else "₽"
                    
                    # Статус
                    status_icon = {
                        OrderStatus.PAID: "✅",
                        OrderStatus.PENDING: "⏳",
                        OrderStatus.FAILED: "❌",
                        OrderStatus.REFUNDED: "↩️",
                    }.get(p.status, "❔")
                    
                    # Провайдер
                    provider_name = {
                        PaymentProvider.YOOKASSA: "ЮKassa",
                        PaymentProvider.STRIPE: "Stripe",
                        PaymentProvider.STARS: "⭐ Stars",
                    }.get(p.provider, p.provider.value if p.provider else "—")
                    
                    # Форматируем дату
                    date_str = p.created_at.strftime("%d.%m %H:%M") if p.created_at else "—"
                    
                    text += (
                        f"• {status_icon} <code>{p.payment_id[:12]}...</code> "
                        f"| {p.user_id} | {p.amount:.0f}{currency} "
                        f"| {provider_name} | {date_str}\n"
                    )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_payments")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
            
            await safe_edit_message(callback.message, text, keyboard)
            
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки платежей: {e}")
        await safe_edit_message(
            callback.message,
            f"❌ Ошибка загрузки платежей: {e}",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )
    
    await callback.answer()