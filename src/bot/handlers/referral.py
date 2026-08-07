from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.referral_repository import ReferralRepository
from src.db.models import ReferralBonusStatus, User
from src.db.session import async_session
from src.utils.sentry import SentryStub

router = Router()

logger = logging.getLogger(__name__)


def get_referral_link(referral_code: str) -> str:
    """Генерирует глубокую реферальную ссылку с ?ref=CODE.

    Используется формат: t.me/BOT_USERNAME?start=ref_CODE
    Бот (start.py) парсит `ref_CODE` → CODE, находит реферера по referral_code
    и привязывает referred_by.
    """
    username = settings.BOT_USERNAME or "laosllebot"
    clean_username = username.lstrip("@")
    return f"https://t.me/{clean_username}?start=ref_{referral_code}"


def get_referral_link_legacy(telegram_id: int) -> str:
    """Legacy-вариант для обратной совместимости (сырой telegram_id)."""
    username = settings.BOT_USERNAME or "laosllebot"
    return f"https://t.me/{username.lstrip('@')}?start={telegram_id}"


def _status_icon(status: ReferralBonusStatus) -> str:
    return {
        ReferralBonusStatus.HELD: "⏳",
        ReferralBonusStatus.RELEASED: "✅",
        ReferralBonusStatus.CANCELLED: "❌",
    }.get(status, "❔")


def _status_label(status_value: str) -> str:
    mapping = {
        ReferralBonusStatus.HELD.value: "Заморожен (ожидает первой оплаты)",
        ReferralBonusStatus.RELEASED.value: "Начислено",
        ReferralBonusStatus.CANCELLED.value: "Отменено",
    }
    return mapping.get(status_value, status_value)


async def build_referral_text(user, session=None) -> str:
    stats = await ReferralRepository.get_referrer_stats(user.telegram_id)
    link = get_referral_link(user.referral_code) if user.referral_code else get_referral_link_legacy(user.telegram_id)

    own_bonus_info = ""
    try:
        # Если переданная сессия активна, используем её для загрузки данных
        if session:
            # Убеждаемся, что данные загружены через сессию
            if not hasattr(user, 'bonuses_as_referred') or not user.bonuses_as_referred:
                # Пробуем загрузить через сессию
                stmt = select(User).where(User.telegram_id == user.telegram_id).options(selectinload(User.bonuses_as_referred))
                user_refreshed = await session.execute(stmt)
                user = user_refreshed.scalar_one_or_none()
                
        # Теперь пробуем получить бонус
        own_bonus = None
        if user and hasattr(user, 'bonuses_as_referred'):
            for bonus in user.bonuses_as_referred:
                if bonus.referred_id == user.telegram_id:
                    own_bonus = bonus
                    break
        
        if own_bonus:
            status_label = _status_label(own_bonus.status.value)
            icon = _status_icon(own_bonus.status)
            own_bonus_info = (
                f"\n🎟 <b>Ваш бонус за приглашение:</b>\n"
                f"  Статус: {icon} <i>{status_label}</i>\n"
                f"  Вам полагается: +{own_bonus.referred_days} дн. подписки\n"
                f"  Реферер ID: <code>{own_bonus.referrer_id}</code>\n"
            )
    except Exception as e:
        SentryStub.capture_exception(e, context="build_referral_text.own_bonus")

    total_pending_days = stats["held_days"]
    total_earned = stats["total_days_earned"]

    parts = [
        "🎁 <b>Реферальная система</b>",
        "",
        "Приглашай друзей и получай бонусы!",
        "",
        f"<b>Твоя ссылка (глубокая, ?ref=CODE):</b>",
        f"<code>{link}</code>",
        "",
        f"🏷 <b>Твой реф-код:</b> <code>{user.referral_code or '-'}</code>",
        "",
        "<b>Статистика приглашённых:</b>",
        f"👥 Всего приглашено: <b>{stats['total_referred']}</b>",
        f"✅ Начислено бонусов: <b>{stats['released_count']}</b>",
        f"⏳ Ожидают оплаты (HELD): <b>{stats['held_count']}</b>",
        f"❌ Отменено: <b>{stats['cancelled_count']}</b>",
        "",
        "<b>Полученные дни:</b>",
        f"💎 Заработано: <b>+{total_earned} дн.</b>",
        f"🔒 В ожидании (заморожено): <b>+{total_pending_days} дн.</b>",
        "",
        "<b>Бонусы (после ПЕРВОЙ успешной оплаты рефералом):</b>",
        f"• Приглашённый пользователь: <b>+{settings.REFERRAL_BONUS_REFERRED_DAYS} день</b>",
        f"• Ты за каждого реферала: <b>+{settings.REFERRAL_BONUS_REFERRER_DAYS} дня</b>",
        "",
        "⚠️ <b>Важно:</b> Бонусы начисляются не за регистрацию, а только после ПЕРВОЙ оплаты!",
    ]
    if own_bonus_info:
        parts.append(own_bonus_info)
    return "\n".join(parts)


def referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="subscribe_buy")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")],
    ])


@router.message(Command("ref"))
async def ref_command(message: Message):
    try:
        user_id = message.from_user.id
        
        # Используем сессию для загрузки пользователя с бонусами
        async with async_session() as session:
            stmt = select(User).where(User.telegram_id == user_id).options(selectinload(User.bonuses_as_referred))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                # Если пользователь не найден, создаем нового
                user, _ = await UserRepository.get_or_create(
                    telegram_id=user_id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                )
                # Обновляем пользователя с бонусами
                stmt = select(User).where(User.telegram_id == user_id).options(selectinload(User.bonuses_as_referred))
                result = await session.execute(stmt)
                user = result.scalar_one()
            
            text = await build_referral_text(user, session)
            
        await message.answer(text, reply_markup=referral_keyboard(), parse_mode="HTML")
    except Exception as e:
        SentryStub.capture_exception(e, context="ref_command", user_id=message.from_user.id)
        await message.answer("❌ Ошибка загрузки реферального меню.")


@router.callback_query(F.data == "referral_menu")
async def referral_menu_callback(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        
        async with async_session() as session:
            stmt = select(User).where(User.telegram_id == user_id).options(selectinload(User.bonuses_as_referred))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                user, _ = await UserRepository.get_or_create(
                    telegram_id=user_id,
                    username=callback.from_user.username,
                    first_name=callback.from_user.first_name,
                    last_name=callback.from_user.last_name,
                )
                stmt = select(User).where(User.telegram_id == user_id).options(selectinload(User.bonuses_as_referred))
                result = await session.execute(stmt)
                user = result.scalar_one()
            
            text = await build_referral_text(user, session)
            
        try:
            await callback.message.edit_text(text, reply_markup=referral_keyboard(), parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=referral_keyboard(), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        SentryStub.capture_exception(e, context="referral_menu_callback", user_id=callback.from_user.id)
        await callback.answer("❌ Ошибка", show_alert=True)