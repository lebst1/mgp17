from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.subscription_repository import SubscriptionRepository
from src.config import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("subscribe"))
async def subscribe_info(message: Message):
    """Информация о подписке"""
    user_id = message.from_user.id
    
    subscription = await SubscriptionRepository.get_or_create_subscription(user_id)
    
    days_left = 0
    if subscription.expires_at:
        days_left = (subscription.expires_at - datetime.utcnow()).days
    
    text = f"""
💳 <b>Подписка SafeSaverX</b>

📅 <b>Статус:</b> {'✅ Активна' if subscription.is_active and days_left > 0 else '❌ Неактивна'}
📆 <b>Действует до:</b> {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}
📝 <b>Тип:</b> {subscription.subscription_type}
📊 <b>Осталось дней:</b> {days_left if days_left > 0 else '0'}

<b>💰 Цена:</b> 99₽ / месяц

<b>👥 Реферальная программа:</b>
Приведи друга и получи +5 дней бесплатно!

<b>📌 Команды:</b>
/subscribe — информация о подписке
/referral — реферальная ссылка
/buy — купить подписку
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Купить 99₽", callback_data="subscribe_buy"),
            InlineKeyboardButton(text="👥 Рефералка", callback_data="subscribe_referral")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")
        ]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "subscribe_buy")
async def subscribe_buy(callback: CallbackQuery):
    """Оплата подписки"""
    await callback.answer()
    
    await callback.message.edit_text(
        "💳 <b>Оплата подписки</b>\n\n"
        "Скоро здесь появится возможность оплаты.\n"
        "А пока ты можешь использовать реферальную систему!\n\n"
        "👥 Приведи друга и получи +5 дней бесплатно.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Рефералка", callback_data="subscribe_referral")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="subscribe_back")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == "subscribe_referral")
async def subscribe_referral(callback: CallbackQuery):
    """Реферальная система"""
    await callback.answer()
    
    user_id = callback.from_user.id
    bot_username = settings.BOT_USERNAME or "laosllebot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    # Получаем информацию о подписке
    subscription = await SubscriptionRepository.get_or_create_subscription(user_id)
    days_left = 0
    if subscription.expires_at:
        days_left = (subscription.expires_at - datetime.utcnow()).days
    
    text = f"""
👥 <b>Реферальная программа</b>

За каждого приведенного друга ты получаешь <b>+5 дней</b> бесплатной подписки!

<b>Твоя реферальная ссылка:</b>
<code>{ref_link}</code>

📋 <b>Как это работает:</b>
1. Отправь ссылку другу
2. Друг переходит по ссылке и запускает бота
3. Ты получаешь +5 дней к подписке
4. Друг получает 1 день бесплатно

<b>Твой баланс:</b>
📊 Осталось дней: {days_left if days_left > 0 else '0'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data="copy_referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscribe_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "copy_referral")
async def copy_referral(callback: CallbackQuery):
    """Копирование реферальной ссылки"""
    user_id = callback.from_user.id
    bot_username = settings.BOT_USERNAME or "laosllebot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    await callback.answer(
        text=f"📋 Ссылка скопирована!\n\n{ref_link}",
        show_alert=True
    )


@router.callback_query(lambda c: c.data == "subscribe_back")
async def subscribe_back(callback: CallbackQuery):
    """Назад к подписке"""
    await callback.answer()
    await subscribe_info(callback.message)


@router.message(Command("referral"))
async def referral_command(message: Message):
    """Реферальная ссылка"""
    # Создаем подписку если её нет
    await SubscriptionRepository.get_or_create_subscription(message.from_user.id)
    
    user_id = message.from_user.id
    bot_username = settings.BOT_USERNAME or "laosllebot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    subscription = await SubscriptionRepository.get_or_create_subscription(user_id)
    days_left = 0
    if subscription.expires_at:
        days_left = (subscription.expires_at - datetime.utcnow()).days
    
    text = f"""
👥 <b>Твоя реферальная ссылка</b>

<code>{ref_link}</code>

📋 <b>Как это работает:</b>
1. Отправь ссылку другу
2. Друг переходит по ссылке и запускает бота
3. Ты получаешь +5 дней к подписке
4. Друг получает 1 день бесплатно

<b>Твой баланс:</b>
📊 Осталось дней: {days_left if days_left > 0 else '0'}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data="copy_referral")],
        [InlineKeyboardButton(text="💳 Подписка", callback_data="subscribe_back")]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("buy"))
async def buy_command(message: Message):
    """Купить подписку"""
    await subscribe_buy(message)