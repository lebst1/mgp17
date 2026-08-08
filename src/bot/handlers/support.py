from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.config import settings
from src.db.repositories.user_repository import UserRepository
from src.utils.sentry import SentryStub

router = Router()


class SupportStates(StatesGroup):
    waiting_for_message = State()


@router.message(Command("support"))
async def support_command(message: Message, state: FSMContext):
    """Команда /support — открывает форму обращения в поддержку"""
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
    
    text = """
🆘 <b>Поддержка SafeSaverX</b>

Опишите вашу проблему или вопрос.
Мы ответим вам в ближайшее время!

📌 <b>Что можно писать:</b>
• Проблемы с подключением бота
• Вопросы по подписке
• Ошибки и баги
• Предложения по улучшению

✏️ Напишите ваше сообщение ниже.
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_start")],
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(SupportStates.waiting_for_message)


@router.callback_query(F.data == "support")
async def support_callback(callback: CallbackQuery, state: FSMContext):
    """Кнопка поддержки из меню"""
    await callback.answer()
    
    user = await UserRepository.get_by_id(callback.from_user.id)
    if not user:
        await callback.message.answer("❌ Пользователь не найден. Попробуйте /start")
        return
    
    text = """
🆘 <b>Поддержка SafeSaverX</b>

Опишите вашу проблему или вопрос.
Мы ответим вам в ближайшее время!

📌 <b>Что можно писать:</b>
• Проблемы с подключением бота
• Вопросы по подписке
• Ошибки и баги
• Предложения по улучшению

✏️ Напишите ваше сообщение ниже.
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_start")],
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    await state.set_state(SupportStates.waiting_for_message)


@router.message(SupportStates.waiting_for_message)
async def support_send_message(message: Message, state: FSMContext, bot: Bot):
    """Отправляет сообщение владельцу"""
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        await state.clear()
        return
    
    # Проверяем, не отмена ли это
    if message.text and message.text.lower() == "/cancel":
        await message.answer("❌ Отправка отменена.")
        await state.clear()
        return
    
    # Формируем информацию о пользователе
    user_info = f"""
<b>🆘 Новое обращение в поддержку</b>

👤 Пользователь: {user.first_name or 'Без имени'}
🆔 ID: <code>{user.telegram_id}</code>
📛 Username: @{user.username or 'Нет'}
💳 Подписка: {'✅ Активна' if user.has_active_subscription() else '❌ Истекла'}
📝 Сохранено сообщений: {user.messages_saved or 0}

📩 <b>Сообщение:</b>
<blockquote>{message.text or 'Без текста'}</blockquote>
"""
    
    # Клавиатура для ответа
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💬 Ответить",
                callback_data=f"support_reply_{user.telegram_id}"
            ),
            InlineKeyboardButton(
                text="✅ Закрыть обращение",
                callback_data=f"support_close_{user.telegram_id}"
            )
        ]
    ])
    
    # Отправляем владельцу
    try:
        await bot.send_message(
            chat_id=settings.OWNER_TELEGRAM_ID,
            text=user_info,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await message.answer(
            "✅ Ваше сообщение отправлено в поддержку!\n\n"
            "Мы ответим вам в ближайшее время.\n"
            "Не закрывайте бота, чтобы получить уведомление о ответе.",
            parse_mode="HTML"
        )
        await state.clear()
        
    except Exception as e:
        SentryStub.capture_exception(e, context="support_send_message", user_id=user.telegram_id)
        await message.answer("❌ Ошибка отправки. Попробуйте позже.")
        await state.clear()


@router.callback_query(F.data.startswith("support_reply_"))
async def support_reply(callback: CallbackQuery, state: FSMContext):
    """Начать ответ пользователю"""
    user_id = int(callback.data.split("_")[-1])
    
    await state.update_data(reply_user_id=user_id)
    await state.set_state(SupportStates.waiting_for_message)
    
    await callback.message.answer(
        f"✏️ Введите ответ для пользователя <code>{user_id}</code>:\n\n"
        f"Отправьте /cancel чтобы отменить.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(SupportStates.waiting_for_message)
async def support_reply_send(message: Message, state: FSMContext, bot: Bot):
    """Отправляет ответ пользователю"""
    data = await state.get_data()
    user_id = data.get("reply_user_id")
    
    if not user_id:
        await message.answer("❌ Ошибка: пользователь не найден")
        await state.clear()
        return
    
    if message.text and message.text.lower() == "/cancel":
        await message.answer("❌ Отправка ответа отменена.")
        await state.clear()
        return
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"📩 <b>Ответ поддержки</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        
        await message.answer(
            f"✅ Ответ отправлен пользователю <code>{user_id}</code>",
            parse_mode="HTML"
        )
        await state.clear()
        
    except Exception as e:
        SentryStub.capture_exception(e, context="support_reply_send", user_id=user_id)
        await message.answer(f"❌ Ошибка отправки: {e}")


@router.callback_query(F.data.startswith("support_close_"))
async def support_close(callback: CallbackQuery):
    """Закрывает обращение"""
    await callback.answer("✅ Обращение закрыто")
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Обращение закрыто",
        reply_markup=None
    )


@router.message(Command("cancel"))
async def cancel_support(message: Message, state: FSMContext):
    """Отмена действия"""
    await state.clear()
    await message.answer("❌ Действие отменено.")