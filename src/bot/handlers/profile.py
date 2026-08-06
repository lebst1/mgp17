from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from src.config import settings
from src.db.repositories.user_repository import UserRepository

router = Router()


def _format_date(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


async def build_profile_text(user) -> str:
    sub = user.get_subscription_info()
    until = _format_date(sub["subscription_until"])

    return f"""
👤 <b>Личный кабинет</b>

🆔 ID: <code>{user.telegram_id}</code>
📛 Username: @{user.username or 'не указан'}
📅 Дата регистрации: {_format_date(user.created_at)}

💳 <b>Подписка</b>
▸ Статус: {sub['status']}
▸ Действует до: {until}
▸ Осталось дней: {sub['days_left']}

🎁 <b>Рефералы</b>
▸ Приглашено: {user.referrals_count or 0}
▸ Заработано дней: {user.referral_days_earned or 0}
"""


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Рефералы", callback_data="referral_menu")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="subscribe_buy")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")],
    ])


@router.message(Command("profile"))
async def profile_command(message: Message):
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        user, _ = await UserRepository.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

    text = await build_profile_text(user)
    await message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "profile_menu")
async def profile_callback(callback: CallbackQuery):
    user = await UserRepository.get_by_id(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    text = await build_profile_text(user)
    try:
        await callback.message.edit_text(text, reply_markup=profile_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")
    await callback.answer()
