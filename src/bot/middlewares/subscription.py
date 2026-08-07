from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
import asyncio
import logging

from src.config import settings
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.subscription_repository import SubscriptionRepository
from src.services.yookassa_service import YooKassaService
from src.db.models import OrderStatus
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)

router = Router()

_POLL_MAX_ATTEMPTS = 60


def trim_text(text: str, max_len: int = 4000) -> str:
    if len(text) > max_len:
        return text[:max_len] + "\n\n... (сообщение обрезано)"
    return text


def _format_until(user) -> str:
    info = user.get_subscription_info()
    if info["subscription_until"]:
        return info["subscription_until"].strftime("%d.%m.%Y %H:%M")
    return "—"


def _order_status_label(status_value: str) -> str:
    mapping = {
        OrderStatus.PENDING.value: "⏳ Ожидает оплаты",
        OrderStatus.PAID.value: "✅ Оплачено",
        OrderStatus.FAILED.value: "❌ Отклонено",
        OrderStatus.REFUNDED.value: "↩️ Возвращено",
    }
    return mapping.get(status_value, f"❔ {status_value}")


async def _build_subscribe_text(user) -> str:
    info = user.get_subscription_info()
    return trim_text(f"""
💳 <b>Подписка SafeSaverX</b>

📅 <b>Статус:</b> {info['status']}
📆 <b>Действует до:</b> {_format_until(user)}
📊 <b>Осталось дней:</b> {info['days_left']}

<b>💰 Цена:</b> {settings.SUBSCRIPTION_PRICE:.0f}₽ / {settings.SUBSCRIPTION_DAYS} дней

<b>Что дает подписка:</b>
✅ Сохранение удаленных сообщений
✅ Уведомления о правках
✅ Сохранение медиа-файлов
✅ Полный доступ ко всем функциям бота
""")


def _subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Купить {settings.SUBSCRIPTION_PRICE:.0f}₽", callback_data="subscribe_buy")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")],
    ])


def _payment_pending_keyboard(payment_id: str, payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
        [InlineKeyboardButton(
            text="🔄 Автопроверка...",
            callback_data=f"check_payment_{payment_id}",
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscribe_menu")],
    ])


def _payment_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Моя подписка", callback_data="subscribe_menu")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")],
    ])


async def _poll_payment_status(
    bot,
    chat_id: int,
    message_id: int,
    user_id: int,
    payment_id: str,
    poll_interval: int = 3,
    max_attempts: int = _POLL_MAX_ATTEMPTS,
) -> None:
    attempt = 0
    last_shown_status = None
    try:
        while attempt < max_attempts:
            attempt += 1
            try:
                result = await YooKassaService.check_payment(payment_id)
                if not result:
                    await asyncio.sleep(poll_interval)
                    continue

                order_status = result.get("order_status", OrderStatus.PENDING.value)
                if result.get("paid") or order_status in (OrderStatus.PAID.value, OrderStatus.FAID.value, OrderStatus.REFUNDED.value):
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=_format_payment_result_text(result, user_id),
                            reply_markup=_payment_result_keyboard(),
                            parse_mode="HTML",
                        )
                    except Exception as edit_err:
                        logger.debug("Не удалось обновить сообщение о платеже %s: %s", payment_id, edit_err)
                    return

                if last_shown_status != order_status and (attempt % 4 == 0 or attempt == 1):
                    last_shown_status = order_status
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=_format_payment_pending_text(
                                payment_id=payment_id,
                                amount=result.get("amount", settings.SUBSCRIPTION_PRICE),
                                status_label=_order_status_label(order_status),
                                attempt=attempt,
                                max_attempts=max_attempts,
                            ),
                            reply_markup=_payment_pending_keyboard(
                                payment_id=payment_id,
                                payment_url=result.get("payment_url", f"https://yoomoney.ru"),
                            ) if result.get("payment_url") else None,
                            parse_mode="HTML",
                        )
                    except Exception as edit_err:
                        logger.debug("Не удалось обновить прогресс платежа %s: %s", payment_id, edit_err)
            except Exception as poll_err:
                SentryStub.capture_exception(
                    poll_err, context="_poll_payment_status.iter",
                    payment_id=payment_id, attempt=attempt,
                )
            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        logger.info("Polling платежа %s отменён", payment_id)
    except Exception as e:
        SentryStub.capture_exception(e, context="_poll_payment_status", payment_id=payment_id)


def _format_payment_pending_text(
    payment_id: str,
    amount: float,
    status_label: str,
    attempt: int,
    max_attempts: int,
) -> str:
    progress_pct = min(100, int(attempt * 100 / max_attempts))
    bar_len = 12
    filled = int(bar_len * attempt / max_attempts)
    bar = "█" * filled + "░" * (bar_len - filled)
    return trim_text(f"""
💳 <b>Оплата подписки</b>

Сумма: <b>{amount:.0f}₽</b>
Срок: <b>{settings.SUBSCRIPTION_DAYS} дней</b>

Статус: {status_label}
Проверка: {attempt}/{max_attempts} [{bar}] {progress_pct}%

<i>Статус проверяется автоматически каждые {settings.PAYMENT_POLL_INTERVAL_SEC} секунды.
После оплаты подписка активируется мгновенно.</i>
""")


def _format_payment_result_text(result: dict, user_id: int) -> str:
    order_status = result.get("order_status", "")
    if result.get("paid") or order_status == OrderStatus.PAID.value:
        parts = [
            "✅ <b>Подписка активирована!</b>",
            "",
            f"Сумма: <b>{result.get('amount', settings.SUBSCRIPTION_PRICE):.0f}₽</b>",
            f"Срок действия: <b>{settings.SUBSCRIPTION_DAYS} дней</b>",
        ]
        if result.get("referral_bonus_released"):
            referred_days = result.get("referred_bonus_days", 0)
            referrer_days = result.get("referrer_bonus_days", 0)
            if referred_days:
                parts.append("")
                parts.append(f"🎁 <b>Реферальный бонус!</b> Вам начислено <b>+{referred_days} дн.</b> подписки за приглашение.")
            if referrer_days:
                parts.append("")
                parts.append(f"💝 Вашему рефереру начислено <b>+{referrer_days} дн.</b>")
        return trim_text("\n".join(parts))

    if order_status == OrderStatus.FAILED.value:
        return trim_text(f"""
❌ <b>Платёж отклонён</b>

Попробуйте снова или используйте другой способ оплаты.
Если проблема сохраняется — напишите в поддержку.
""")

    if order_status == OrderStatus.REFUNDED.value:
        return trim_text("↩️ <b>Возврат средств</b>\n\nПлатёж возвращён.")

    return trim_text(f"⏳ <b>Статус платежа:</b> {_order_status_label(order_status)}")


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


@router.callback_query(F.data == "subscribe_buy")
async def subscribe_buy(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    try:
        if not YooKassaService.is_configured():
            await callback.message.answer(
                "⚠️ Оплата временно недоступна. Обратитесь к администратору.",
                parse_mode="HTML",
            )
            return

        payment_data = await YooKassaService.create_payment(user_id)
        if not payment_data:
            await callback.message.answer("❌ Не удалось создать платёж. Попробуйте позже.")
            return

        payment_id = payment_data["payment_id"]
        payment_url = payment_data["payment_url"]

        sent_msg = await callback.message.answer(
            _format_payment_pending_text(
                payment_id=payment_id,
                amount=payment_data.get("amount", settings.SUBSCRIPTION_PRICE),
                status_label=_order_status_label(payment_data.get("order_status", OrderStatus.PENDING.value)),
                attempt=0,
                max_attempts=_POLL_MAX_ATTEMPTS,
            ),
            reply_markup=_payment_pending_keyboard(payment_id, payment_url),
            parse_mode="HTML",
        )

        loop = asyncio.get_event_loop()
        loop.create_task(_poll_payment_status(
            bot=callback.bot,
            chat_id=sent_msg.chat.id,
            message_id=sent_msg.message_id,
            user_id=user_id,
            payment_id=payment_id,
            poll_interval=settings.PAYMENT_POLL_INTERVAL_SEC,
            max_attempts=_POLL_MAX_ATTEMPTS,
        ))
    except Exception as e:
        SentryStub.capture_exception(e, context="subscribe_buy", user_id=user_id)
        logger.exception("❌ subscribe_buy error user=%s: %s", user_id, e)
        await callback.message.answer("❌ Ошибка создания платежа. Попробуйте позже.")


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    payment_id = callback.data.replace("check_payment_", "")
    try:
        result = await YooKassaService.check_payment(payment_id)
        if not result:
            await callback.answer("❌ Не удалось проверить платёж", show_alert=True)
            return

        if result.get("paid"):
            try:
                await callback.message.edit_text(
                    _format_payment_result_text(result, callback.from_user.id),
                    reply_markup=_payment_result_keyboard(),
                    parse_mode="HTML",
                )
            except Exception:
                await callback.message.answer(
                    _format_payment_result_text(result, callback.from_user.id),
                    reply_markup=_payment_result_keyboard(),
                    parse_mode="HTML",
                )
            await callback.answer("✅ Оплата прошла успешно!", show_alert=True)
        else:
            status_label = _order_status_label(result.get("order_status", OrderStatus.PENDING.value))
            await callback.answer(f"⏳ {status_label}", show_alert=True)
    except Exception as e:
        SentryStub.capture_exception(e, context="check_payment", payment_id=payment_id)
        await callback.answer("❌ Ошибка проверки платежа", show_alert=True)


@router.callback_query(F.data == "subscribe_back")
async def subscribe_back(callback: CallbackQuery):
    await callback.answer()
    user = await SubscriptionRepository.get_or_create_subscription(callback.from_user.id)
    text = await _build_subscribe_text(user)
    try:
        await callback.message.edit_text(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=_subscribe_keyboard(), parse_mode="HTML")