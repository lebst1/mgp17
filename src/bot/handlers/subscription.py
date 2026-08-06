from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
import logging

from src.config import settings
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.subscription_repository import SubscriptionRepository
from src.services.yookassa_service import YooKassaService

logger = logging.getLogger(__name__)

router = Router()


def trim_text(text: str, max_len: int = 4000) -> str:
    if len(text) > max_len:
        return text[:max_len] + "\n\n... (сообщение обрезано)"
    return text


def _format_until(user) -> str:
    info = user.get_subscription_info()
    if info["subscription_until"]:
        return info["subscription_until"].strftime("%d.%m.%Y %H:%M")
    return "—"


async def _build_subscribe_text(user) -> str:
    info = user.get_subscription_info()
    return trim_text(f"""
💳 <b>Подписка SafeSaverX</b>

📅 <b>Статус:</b> {info['status']}
📆 <b>Действует до:</b> {_format_until(user)}
📊 <b>Осталось дней:</b> {info['days_left']}

<b>💰 Цена:</b> {settings.SUBSCRIPTION_PRICE:.0f}₽ / {settings.SUBSCRIPTION_DAYS} дней

📌 <b>Команды:</b>
/subscribe — информация о подписке
/buy — купить подписку
""")


def _subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Купить {settings.SUBSCRIPTION_PRICE:.0f}₽", callback_data="subscribe_buy")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")],
    ])


@router.message(Command("subscribe"))
async def subscribe_info(message: Message):
    user = await SubscriptionRepository.get_or_create_subscription(message.from_user.id)
    text = await _build_subscribe_text(user)
    await message.answer(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")


@router.message(Command("buy"))
async def buy_command(message: Message):
    await subscribe_info(message)


@router.callback_query(F.data == "subscribe_menu")
async def subscribe_menu_callback(callback: CallbackQuery):
    user = await SubscriptionRepository.get_or_create_subscription(callback.from_user.id)
    text = await _build_subscribe_text(user)
    try:
        await callback.message.edit_text(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "subscribe_buy")
async def subscribe_buy(callback: CallbackQuery):
    await callback.answer()

    if not YooKassaService.is_configured():
        await callback.message.answer(
            "⚠️ Оплата временно недоступна. Обратитесь к администратору.",
            parse_mode="HTML",
        )
        return

    payment_data = await YooKassaService.create_payment(callback.from_user.id)
    if not payment_data:
        await callback.message.answer("❌ Не удалось создать платёж. Попробуйте позже.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=payment_data["payment_url"])],
        [InlineKeyboardButton(
            text="✅ Проверить оплату",
            callback_data=f"check_payment_{payment_data['payment_id']}",
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscribe_menu")],
    ])

    await callback.message.answer(
        trim_text(
            f"💳 <b>Оплата подписки</b>\n\n"
            f"Сумма: <b>{settings.SUBSCRIPTION_PRICE:.0f}₽</b>\n"
            f"Срок: <b>{settings.SUBSCRIPTION_DAYS} дней</b>\n\n"
            f"Нажми «Оплатить», затем «Проверить оплату»."
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    payment_id = callback.data.replace("check_payment_", "")
    result = await YooKassaService.check_payment(payment_id)

    if not result:
        await callback.answer("❌ Не удалось проверить платёж", show_alert=True)
        return

    if result["paid"]:
        user_id = result["user_id"] or callback.from_user.id
        user = await UserRepository.extend_subscription(user_id, settings.SUBSCRIPTION_DAYS)
        until = user.subscription_until.strftime("%d.%m.%Y %H:%M") if user else "—"
        await callback.answer("✅ Оплата прошла успешно!", show_alert=True)
        await callback.message.answer(
            f"✅ <b>Подписка активирована!</b>\n\n"
            f"Действует до: <b>{until}</b>",
            parse_mode="HTML",
        )
        logger.info(f"✅ Подписка активирована для {user_id} через платёж {payment_id}")
    else:
        await callback.answer(f"⏳ Статус: {result['status']}", show_alert=True)


@router.callback_query(F.data == "subscribe_back")
async def subscribe_back(callback: CallbackQuery):
    await callback.answer()
    user = await SubscriptionRepository.get_or_create_subscription(callback.from_user.id)
    text = await _build_subscribe_text(user)
    await callback.message.edit_text(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")
