from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile, CopyTextButton
from aiogram.filters import Command, CommandStart
import os
import logging
import re

from src.config import settings
from src.db.repositories.user_repository import UserRepository
from src.db.repositories.business_repository import BusinessRepository
from src.db.repositories.referral_repository import ReferralRepository
from src.utils.sentry import SentryStub

logger = logging.getLogger(__name__)

router = Router()

_REF_PATTERNS = [
    re.compile(r"^ref_([A-Za-z0-9]+)$", re.IGNORECASE),
    re.compile(r"^r_([A-Za-z0-9]+)$", re.IGNORECASE),
]


def _extract_referral_code(raw_deeplink: str) -> str | None:
    if not raw_deeplink:
        return None
    arg = raw_deeplink.strip()
    if not arg:
        return None
    for pattern in _REF_PATTERNS:
        m = pattern.match(arg)
        if m:
            return m.group(1)
    if arg.isdigit():
        return arg
    if len(arg) >= 6 and len(arg) <= 32 and re.match(r"^[A-Za-z0-9]+$", arg):
        return arg
    return None


async def get_main_menu(user, has_business):
    referred_note = ""
    if user.referred_by:
        try:
            from src.db.models import ReferralBonusStatus
            if hasattr(user, 'bonuses_as_referred'):
                for bonus in user.bonuses_as_referred:
                    if bonus.referred_id == user.telegram_id:
                        if bonus.status == ReferralBonusStatus.RELEASED:
                            referred_note = f"\n🎁 <i>Реф-бонус начислен: +{bonus.referred_days} дн.</i>"
                        break
        except Exception:
            pass

    text = f"""
<b>SafeSaverX</b>

👤 <b>Профиль</b>
▸ Статус: <b>{'активен' if user.is_active else 'неактивен'}</b>
▸ Business: <b>{'подключен' if has_business else 'не подключен'}</b>{referred_note}

📌 <b>Как подключить бота:</b>
1. Нажми «📋 Скопировать юзернейм»
2. Открой Настройки Telegram → Редактирование профиля
3. Выбери «Автоматизация чатов»
4. Вставь скопированный юзернейм
5. Дай ВСЕ разрешения на сообщения
6. Нажми «Добавить»

<b>Что умеет бот:</b>
• Сохраняет ВСЕ медиа (фото, видео, голосовые)
• Присылает уведомления об удалении/правке
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📋 Скопировать юзернейм",
                copy_text=CopyTextButton(
                    text=f"@{settings.BOT_USERNAME.lstrip('@')}"
                )
            )
        ],
        [
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"),
        ],
    ])

    return text, keyboard


async def send_main_menu(target, user, has_business):
    text, keyboard = await get_main_menu(user, has_business)
    photo_path = "assets/menu.jpg"

    if os.path.exists(photo_path):
        photo = FSInputFile(photo_path)
        await target.answer_photo(
            photo=photo,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(CommandStart())
async def start_command(message: Message):
    referral_code = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        referral_code = _extract_referral_code(args[1])

    user, is_new = None, False
    try:
        user, is_new = await UserRepository.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            referral_code=referral_code,
            bot=message.bot,
        )
    except Exception as e:
        SentryStub.capture_exception(e, context="start_command.get_or_create")
        logger.exception("Ошибка get_or_create в /start: %s", e)
        await message.answer("❌ Ошибка инициализации. Попробуйте ещё раз через несколько секунд.")
        return

    # Уведомление о новом пользователе
    if is_new:
        try:
            from datetime import datetime
            user_info = f"""
👤 <b>Новый пользователь!</b>

🆔 ID: <code>{user.telegram_id}</code>
👤 Имя: {user.first_name or 'Не указано'}
📛 Username: @{user.username or 'Нет'}
📅 Зарегистрирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}
🔗 Реферал: {'Да' if referral_code else 'Нет'}
"""
            await message.bot.send_message(
                chat_id=settings.OWNER_TELEGRAM_ID,
                text=user_info,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление о новом пользователе: {e}")

    if referral_code and is_new:
        try:
            resolved = await UserRepository.resolve_referral_code(referral_code)
            if resolved and resolved != message.from_user.id:
                await message.answer(
                    "🔗 <b>Приглашение принято!</b>\n\n"
                    "Вы были приглашены реферальной ссылкой. "
                    "🎁 Бонус за приглашение начислен <b>СРАЗУ</b>!",
                    parse_mode="HTML",
                )
        except Exception as e:
            SentryStub.capture_exception(e, context="start_command.referral_greeting")

    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    has_business = len(connections) > 0

    await send_main_menu(message, user, has_business)


@router.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    await callback.answer()

    user = await UserRepository.get_by_id(callback.from_user.id)
    if not user:
        user, _ = await UserRepository.get_or_create(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            bot=callback.bot,
        )

    connections = await BusinessRepository.get_user_connections(callback.from_user.id)
    has_business = len(connections) > 0

    try:
        await callback.message.delete()
    except Exception:
        pass

    await send_main_menu(callback.message, user, has_business)