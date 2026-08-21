from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.db.repositories.user_repository import UserRepository
from src.db.models import ReferralBonusStatus, User
from src.db.session import async_session

router = Router()


def _format_date(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


async def build_profile_text(user) -> str:
    # Подсчет рефералов через связь direct_referrals
    referrals_count = len(user.direct_referrals) if user.direct_referrals else 0
    
    # Подсчет заработанных дней через бонусы (только выпущенные)
    referral_days_earned = 0
    if user.bonuses_as_referrer:
        for bonus in user.bonuses_as_referrer:
            if bonus.status == ReferralBonusStatus.RELEASED:
                referral_days_earned += bonus.referrer_days

    return f"""
👤 <b>Личный кабинет</b>

🆔 ID: <code>{user.telegram_id}</code>
📛 Username: @{user.username or 'не указан'}
📅 Дата регистрации: {_format_date(user.created_at)}

🎁 <b>Рефералы</b>
▸ Приглашено: {referrals_count}
▸ Заработано дней: {referral_days_earned}
"""


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Рефералы", callback_data="referral_menu")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")],
    ])


@router.message(Command("profile"))
async def profile_command(message: Message):
    user_id = message.from_user.id
    
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .where(User.telegram_id == user_id)
            .options(
                selectinload(User.direct_referrals),
                selectinload(User.bonuses_as_referrer)
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user, _ = await UserRepository.get_or_create(
                telegram_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            result = await session.execute(
                select(User)
                .where(User.telegram_id == user_id)
                .options(
                    selectinload(User.direct_referrals),
                    selectinload(User.bonuses_as_referrer)
                )
            )
            user = result.scalar_one()

    text = await build_profile_text(user)
    await message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "profile_menu")
async def profile_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .where(User.telegram_id == user_id)
            .options(
                selectinload(User.direct_referrals),
                selectinload(User.bonuses_as_referrer)
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

    text = await build_profile_text(user)
    try:
        await callback.message.edit_text(text, reply_markup=profile_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")
    await callback.answer()