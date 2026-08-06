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


def trim_text(text: str, max_len: int = 4000) -> str:
    if len(text) > max_len:
        return text[:max_len] + "\n\n... (сообщение обрезано)"
    return text


@router.message(Command("subscribe"))
async def subscribe_info(message: Message):
    """Информация о подписке"""
    user_id = message.from_user.id
    
    subscription = await SubscriptionRepository.get_or_create_subscription(user_id)
    
    days_left = 0
    if subscription.expires_at:
        days_left = (subscription.expires_at - datetime.utcnow()).days
    
    text = trim_text(f"""
💳 <b>Подписка SafeSaverX</b>

📅 <b>Статус:</b> {'✅ Активна' if subscription.is_active and days_left > 0 else '❌ Неактивна'}
📆 <b>Действует до:</b> {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}
📝 <b>Тип:</b> {subscription.subscription_type}
📊 <b>Осталось дней:</b> {days_left if days_left > 0 else '0'}

<b>💰 Цена:</b> 99₽ / месяц

📌 <b>Команды:</b>
/subscribe — информация о подписке
/buy — купить подписку
""")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Купить 99₽", callback_data="subscribe_buy")
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
    
    text = trim_text(
        "💳 <b>Оплата подписки</b>\n\n"
        "Скоро здесь появится возможность оплаты.\n\n"
        "🔙 Нажми «Назад», чтобы вернуться."
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="subscribe_back")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == "subscribe_back")
async def subscribe_back(callback: CallbackQuery):
    """Назад к подписке"""
    await callback.answer()
    await subscribe_info(callback.message)


@router.message(Command("buy"))
async def buy_command(message: Message):
    """Купить подписку"""
    await subscribe_info(message)