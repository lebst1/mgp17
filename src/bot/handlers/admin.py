from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.message_repository import MessageRepository
from src.db.repositories.business_repository import BusinessRepository
from src.db.session import cleanup_old_data
from src.config import settings
import os
import logging

logger = logging.getLogger(__name__)

router = Router()


# ✅ СОСТОЯНИЯ ДЛЯ FSM
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()
    waiting_for_ban_reason = State()


# ✅ ПРОВЕРКА АДМИНА
async def is_admin(user_id: int) -> bool:
    if user_id == settings.OWNER_TELEGRAM_ID:
        return True
    user = await UserRepository.get_by_id(user_id)
    return user.is_admin if user else False


# ✅ ГЛАВНОЕ МЕНЮ АДМИНА
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ панели.")
        return
    
    text = """
🔐 <b>Админ панель SafeSaverX</b>

Выберите действие:

📊 <b>Статистика</b> — просмотр данных
📨 <b>Рассылка</b> — отправить сообщение всем
🚫 <b>Бан</b> — заблокировать пользователя
✅ <b>Разбан</b> — разблокировать пользователя
📋 <b>Список пользователей</b> — все пользователи
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
            InlineKeyboardButton(text="🚫 Бан", callback_data="admin_ban"),
            InlineKeyboardButton(text="✅ Разбан", callback_data="admin_unban")
        ],
        [
            InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="🗑️ Очистка БД", callback_data="admin_cleanup"),
            InlineKeyboardButton(text="💾 Бэкап", callback_data="admin_backup")
        ],
        [
            InlineKeyboardButton(text="💚 Статус", callback_data="admin_status")
        ]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ✅ СТАТИСТИКА
@router.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    # Получаем статистику
    from sqlalchemy import select, func
    from src.db.session import async_session
    from src.db.models import User, SavedMessage, BusinessConnection
    
    async with async_session() as session:
        users_count = await session.scalar(select(func.count()).select_from(User))
        messages_count = await session.scalar(select(func.count()).select_from(SavedMessage))
        deleted_count = await session.scalar(
            select(func.count()).select_from(SavedMessage).where(SavedMessage.is_deleted == True)
        )
        connections_count = await session.scalar(select(func.count()).select_from(BusinessConnection))
    
    text = f"""
📊 <b>Статистика SafeSaverX</b>

👤 <b>Пользователи:</b> {users_count or 0}
📝 <b>Всего сообщений:</b> {messages_count or 0}
🗑️ <b>Удалено:</b> {deleted_count or 0}
🔗 <b>Бизнес-подключений:</b> {connections_count or 0}
💾 <b>Медиа на диске:</b> {len(os.listdir(settings.MEDIA_DIR)) if os.path.exists(settings.MEDIA_DIR) else 0}
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
    
    # Получаем всех пользователей
    from sqlalchemy import select
    from src.db.session import async_session
    from src.db.models import User
    
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


@router.message(AdminStates.waiting_for_user_id)
async def process_ban(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
        user = await UserRepository.update_settings(user_id, is_active=False)
        if user:
            await message.answer(f"✅ Пользователь {user_id} заблокирован!")
        else:
            await message.answer(f"❌ Пользователь {user_id} не найден.")
    except ValueError:
        await message.answer("❌ Неверный формат. Отправь числовой ID.")
    
    await state.clear()


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


@router.message(AdminStates.waiting_for_user_id)
async def process_unban(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
        user = await UserRepository.update_settings(user_id, is_active=True)
        if user:
            await message.answer(f"✅ Пользователь {user_id} разблокирован!")
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
    
    from sqlalchemy import select
    from src.db.session import async_session
    from src.db.models import User
    
    async with async_session() as session:
        users = await session.scalars(select(User).limit(20))
    
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
        await callback.message.edit_text("✅ Очистка БД завершена!", parse_mode="HTML")
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
    
    text = f"""
💚 <b>Статус SafeSaverX</b>

📌 Режим: {settings.TELEGRAM_MODE}
👤 Владелец: {settings.OWNER_TELEGRAM_ID}

<b>Система:</b>
🧠 RAM: {psutil.virtual_memory().percent}%
💾 Диск: {psutil.disk_usage('/').percent}%
🔄 Uptime: {int((time.time() - psutil.boot_time()) / 3600)}ч

<b>База данных:</b>
📁 Размер: {os.path.getsize('data/app.db') / 1024 / 1024:.1f} МБ
"""
    
    import time
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]), parse_mode="HTML")
    await callback.answer()


# ✅ НАЗАД
@router.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.answer()
    await admin_panel(callback.message)


# ✅ КОМАНДА /cancel
@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.")