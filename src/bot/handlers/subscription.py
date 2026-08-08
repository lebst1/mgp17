from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.filters import Command
import logging
from datetime import datetime

from src.config import settings
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.subscription_repository import SubscriptionRepository
from src.db.models import OrderStatus, PaymentProvider
from src.db.repositories.payment_repository import PaymentRepository
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)

router = Router()


def _format_until(user) -> str:
    info = user.get_subscription_info()
    if info["subscription_until"]:
        return info["subscription_until"].strftime("%d.%m.%Y %H:%M")
    return "—"


async def _build_subscribe_text(user) -> str:
    info = user.get_subscription_info()
    return f"""
💳 <b>Подписка SafeSaverX</b>

📅 <b>Статус:</b> {info['status']}
📆 <b>Действует до:</b> {_format_until(user)}
📊 <b>Осталось дней:</b> {info['days_left']}

<b>💰 Цена:</b> {settings.SUBSCRIPTION_PRICE_STARS} ⭐ / {settings.SUBSCRIPTION_DAYS} дней

<b>Что дает подписка:</b>
✅ Сохранение удаленных сообщений
✅ Уведомления о правках
✅ Сохранение медиа-файлов
✅ Полный доступ ко всем функциям бота

<i>Оплата через Telegram Stars — безопасно и быстро!</i>
"""


def _subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💳 Купить за {settings.SUBSCRIPTION_PRICE_STARS} ⭐",
            callback_data="subscribe_buy_stars"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")],
    ])


@router.message(Command("subscribe"))
async def subscribe_info(message: Message):
    """Информация о подписке (без кнопки купить)"""
    try:
        user = await SubscriptionRepository.get_or_create_subscription(message.from_user.id)
        text = await _build_subscribe_text(user)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")],
        ])
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        SentryStub.capture_exception(e, context="subscribe_info", user_id=message.from_user.id)
        await message.answer("❌ Ошибка. Попробуйте позже.")


@router.message(Command("pay"))
async def pay_command(message: Message):
    """Команда /pay для покупки подписки"""
    try:
        user = await SubscriptionRepository.get_or_create_subscription(message.from_user.id)
        text = await _build_subscribe_text(user)
        await message.answer(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")
    except Exception as e:
        SentryStub.capture_exception(e, context="pay_command", user_id=message.from_user.id)
        await message.answer("❌ Ошибка. Попробуйте позже.")


@router.message(Command("buy"))
async def buy_command(message: Message):
    """Старая команда /buy для обратной совместимости"""
    await pay_command(message)


@router.callback_query(F.data == "subscribe_menu")
async def subscribe_menu_callback(callback: CallbackQuery):
    try:
        user = await SubscriptionRepository.get_or_create_subscription(callback.from_user.id)
        text = await _build_subscribe_text(user)
        try:
            await callback.message.edit_text(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        SentryStub.capture_exception(e, context="subscribe_menu_callback", user_id=callback.from_user.id)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "subscribe_buy_stars")
async def subscribe_buy_stars(callback: CallbackQuery):
    """Создает инвойс для оплаты Telegram Stars"""
    await callback.answer()
    
    user_id = callback.from_user.id
    user = await UserRepository.get_by_id(user_id)
    if not user:
        await callback.message.answer("❌ Пользователь не найден")
        return

    try:
        # Создаем инвойс
        prices = [LabeledPrice(
            label=f"Подписка на {settings.SUBSCRIPTION_DAYS} дней",
            amount=settings.SUBSCRIPTION_PRICE_STARS * 1
        )]
        
        await callback.bot.send_invoice(
            chat_id=user_id,
            title=f"Подписка SafeSaverX на {settings.SUBSCRIPTION_DAYS} дней",
            description=f"Доступ ко всем функциям бота на {settings.SUBSCRIPTION_DAYS} дней.",
            payload=f"subscription_{user_id}_{int(datetime.now().timestamp())}",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="subscription",
        )
        logger.info(f"💳 Создан инвойс для пользователя {user_id}")
        
    except Exception as e:
        SentryStub.capture_exception(e, context="subscribe_buy_stars", user_id=user_id)
        logger.exception(f"❌ Ошибка создания инвойса: {e}")
        await callback.message.answer("❌ Ошибка создания платежа. Попробуйте позже.")


@router.pre_checkout_query()
async def pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """Подтверждение платежа"""
    try:
        await pre_checkout_query.bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=True,
        )
        logger.info(f"✅ Pre-checkout подтвержден для {pre_checkout_query.from_user.id}")
    except Exception as e:
        SentryStub.capture_exception(e, context="pre_checkout_query")
        await pre_checkout_query.bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="❌ Ошибка платежа. Попробуйте позже."
        )


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    """Обработка успешного платежа"""
    user_id = message.from_user.id
    payment_info = message.successful_payment
    
    logger.info(f"💳 Успешный платеж от {user_id}: {payment_info}")

    try:
        from src.db.models import OrderStatus, PaymentProvider, Transaction, TransactionType, TransactionStatus, Payment, User
        from src.db.repositories.payment_repository import PaymentRepository
        from src.db.repositories.user_repository import UserRepository
        from src.db.session import async_session
        from sqlalchemy import select
        from datetime import datetime
        import json

        # ✅ СОЗДАЕМ ПЛАТЕЖ И ТРАНЗАКЦИЮ ВРУЧНУЮ
        async with async_session() as session:
            # 1. Создаем платеж
            payment = Payment(
                user_id=user_id,
                payment_id=payment_info.provider_payment_charge_id,
                amount=payment_info.total_amount // 100,
                status=OrderStatus.PAID,
                provider=PaymentProvider.STARS,
                currency="XTR",
                description=f"Подписка на {settings.SUBSCRIPTION_DAYS} дней через Stars",
                provider_raw=json.dumps({"telegram_payment": payment_info.model_dump()}),
                paid_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(payment)
            await session.flush()

            # 2. Создаем транзакцию
            tx = Transaction(
                user_id=user_id,
                type=TransactionType.SUBSCRIPTION,
                status=TransactionStatus.COMPLETED,
                amount=payment.amount,
                days_credited=settings.SUBSCRIPTION_DAYS,
                payment_id=payment.id,
                description=f"Подписка на {settings.SUBSCRIPTION_DAYS} дней через Stars",
                completed_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(tx)

            # 3. Продлеваем подписку
            user = await session.scalar(
                select(User).where(User.telegram_id == user_id)
            )
            if user:
                user.extend_subscription(settings.SUBSCRIPTION_DAYS)
                user.updated_at = datetime.utcnow()
            else:
                await message.answer("❌ Пользователь не найден")
                return

            await session.commit()

        if user:
            until = user.subscription_until.strftime("%d.%m.%Y %H:%M") if user.subscription_until else "—"
            
            # Уведомление пользователю
            await message.answer(
                f"🎉 <b>Подписка активирована!</b>\n\n"
                f"✅ Оплачено: {payment_info.total_amount // 100} ⭐\n"
                f"📅 Подписка активна до: <b>{until}</b>\n\n"
                f"Теперь вам доступны все функции бота! 🚀",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Информация о подписке", callback_data="subscribe_menu")],
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")],
                ])
            )
            
            logger.info(f"✅ Подписка активирована для {user_id} на {settings.SUBSCRIPTION_DAYS} дней")
            
            # ✅ Проверяем реферальный бонус (первая оплата)
            from src.db.repositories.referral_repository import ReferralRepository
            bonus = await ReferralRepository.get_bonus_for_referred(user_id)
            if bonus and bonus.status.value == "held":
                # Если есть HELD бонус — выпускаем его
                await ReferralRepository.release_bonus_after_first_payment(
                    referred_id=user_id,
                    payment=payment
                )
                await message.answer(
                    "🎁 <b>Реферальный бонус активирован!</b>\n\n"
                    "Вам и вашему рефереру начислены бонусные дни! 🚀",
                    parse_mode="HTML"
                )
        else:
            await message.answer("❌ Ошибка активации подписки. Обратитесь в поддержку.")
            
    except Exception as e:
        SentryStub.capture_exception(e, context="successful_payment", user_id=user_id)
        logger.exception(f"❌ Ошибка активации подписки для {user_id}: {e}")
        await message.answer("❌ Ошибка активации подписки. Обратитесь в поддержку.")