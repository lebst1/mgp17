from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from src.config import settings
from src.db.repositories.user_repository import UserRepository

router = Router()


def get_referral_link(telegram_id: int) -> str:
    username = settings.BOT_USERNAME or "SafeSaverX_bot"
    return f"https://t.me/{username.lstrip('@')}?start={telegram_id}"


async def build_referral_text(user) -> str:
    link = get_referral_link(user.telegram_id)
    return f"""
🎁 <b>Реферальная система</b>

Приглашай друзей и получай бонусы!

<b>Твоя ссылка:</b>
<code>{link}</code>

👥 <b>Количество рефералов:</b> {user.referrals_count or 0}
📅 <b>Получено дней:</b> {user.referral_days_earned or 0}

<b>Бонусы:</b>
• Новый пользователь: <b>+1 день</b>
• Ты за каждого реферала: <b>+3 дня</b>
"""


def referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="subscribe_buy")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")],
    ])


@router.message(Command("ref"))
async def ref_command(message: Message):
    user = await UserRepository.get_by_id(message.from_user.id)
    if not user:
        user, _ = await UserRepository.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

    text = await build_referral_text(user)
    await message.answer(text, reply_markup=referral_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "referral_menu")
async def referral_menu_callback(callback: CallbackQuery):
    user = await UserRepository.get_by_id(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    text = await build_referral_text(user)
    try:
        await callback.message.edit_text(text, reply_markup=referral_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=referral_keyboard(), parse_mode="HTML")
    await callback.answer()
