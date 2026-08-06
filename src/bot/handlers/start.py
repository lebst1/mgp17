from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.filters import Command, CommandStart
import os
import logging
import re

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
    """Извлекает ref-код из deep-link аргумента команды /start.

    Поддерживаемые форматы (для t.me/bot?start=...):
      - `ref_CODE`  → `CODE`
      - `r_CODE`    → `CODE`
      - просто число (legacy telegram_id)
      - `CODE` сам по себе, если совпадает с форматом referral_code
    """
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
    sub = user.get_subscription_info()
    until = sub["subscription_until"].strftime("%d.%m.%Y") if sub["subscription_until"] else "—"

    referred_note = ""
    if user.referred_by:
        try:
            bonus = await ReferralRepository.get_bonus_for_referred(user.telegram_id)
            if bonus:
                from src.db.models import ReferralBonusStatus
                if bonus.status == ReferralBonusStatus.HELD:
                    referred_note = "\n🎟 <i>Вы приглашены. Бонус будет начислен после первой оплаты.</i>"
                elif bonus.status == ReferralBonusStatus.RELEASED:
                    referred_note = f"\n🎁 <i>Реф-бонус начислен: +{bonus.referred_days} дн.</i>"
        except Exception:
            pass

    text = f"""
<b>SafeSaverX</b>

👤 <b>Профиль</b>
▸ Статус: <b>{'активен' if user.is_active else 'неактивен'}</b>
▸ Подписка: <b>{sub['status']}</b> (до {until})
▸ Реф-код: <code>{user.referral_code or '-'}</code>
▸ SAVE MODE: <b>{'включен' if user.savemode_enabled else 'выключен'}</b>
▸ Business: <b>{'подключен' if has_business else 'не подключен'}</b>{referred_note}

📌 <b>Как подключить бота:</b>
1. Нажми «📋 Скопировать юзернейм»
2. Открой Настройки Telegram → Редактирование профиля
3. Выбери «Автоматизация действий»
4. Вставь скопированный юзернейм
5. Дай ВСЕ разрешения!

<b>Что умеет бот:</b>
• Присылает уведомления, когда собеседник удаляет сообщение
• Присылает уведомления, когда собеседник редактирует сообщение
• Сохраняет сгорающие фото, голосовые и видео
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu"),
            InlineKeyboardButton(text="🎁 Рефералы", callback_data="referral_menu"),
        ],
        [
            InlineKeyboardButton(text="💳 Подписка", callback_data="subscribe_menu"),
            InlineKeyboardButton(text="⚙ Настройки", callback_data="settings"),
        ],
        [
            InlineKeyboardButton(text="📋 Скопировать юзернейм", callback_data="copy_username"),
        ],
        [
            InlineKeyboardButton(text="❓ Описание команд", callback_data="show_help"),
            InlineKeyboardButton(text="⭐ Важное", callback_data="important"),
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
        )
    except Exception as e:
        SentryStub.capture_exception(e, context="start_command.get_or_create")
        logger.exception("Ошибка get_or_create в /start: %s", e)
        await message.answer("❌ Ошибка инициализации. Попробуйте ещё раз через несколько секунд.")
        return

    if referral_code and is_new:
        try:
            resolved = await UserRepository.resolve_referral_code(referral_code)
            if resolved and resolved != message.from_user.id:
                await message.answer(
                    "🔗 <b>Приглашение принято!</b>\n\n"
                    "Вы были приглашены реферальной ссылкой. "
                    "🎁 Бонус за приглашение будет начислен <b>после первой успешной оплаты</b> подписки.",
                    parse_mode="HTML",
                )
        except Exception as e:
            SentryStub.capture_exception(e, context="start_command.referral_greeting")

    connections = await BusinessRepository.get_user_connections(message.from_user.id)
    has_business = len(connections) > 0

    await send_main_menu(message, user, has_business)


@router.callback_query(lambda c: c.data == "copy_username")
async def copy_username(callback: CallbackQuery):
    await callback.answer(
        text="✅ @SafeSaverX_bot скопирован!\n\nОткрой Настройки → Редактирование профиля → Автоматизация действий и вставь юзернейм.",
        show_alert=True,
    )


@router.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile(callback: CallbackQuery):
    await callback.answer(
        text="📌 Открой Настройки Telegram → Редактирование профиля → Автоматизация действий → вставь @SafeSaverX_bot",
        show_alert=True,
    )


@router.callback_query(lambda c: c.data == "show_help")
async def show_help(callback: CallbackQuery):
    text = """
❓ <b>Команды SafeSaverX</b>

/start — Главное меню
/profile — Личный кабинет
/ref — Реферальная система
/buy — Купить подписку
/settings — Настройки
/savemode on — Включить SAVE MODE
/savemode off — Выключить SAVE MODE
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")],
    ])

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


@router.callback_query(lambda c: c.data == "important")
async def important(callback: CallbackQuery):
    text = """
⭐ <b>Важное</b>

1️⃣ Дай ВСЕ разрешения на работу с сообщениями
2️⃣ Бот присылает уведомления при удалении/правке
3️⃣ Сохраняет сгорающие фото, голосовые и видео
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")],
    ])

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


@router.callback_query(lambda c: c.data == "settings")
async def show_settings(callback: CallbackQuery):
    text = """
⚙ <b>Настройки</b>

▸ SAVE MODE — включить/выключить сохранение
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 SAVE MODE", callback_data="savemode_settings")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")],
    ])

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


@router.callback_query(lambda c: c.data == "savemode_settings")
async def savemode_settings(callback: CallbackQuery):
    text = """
📝 <b>SAVE MODE</b>

▸ Включить / Выключить сохранение
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Включить", callback_data="savemode_on"),
            InlineKeyboardButton(text="❌ Выключить", callback_data="savemode_off"),
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")],
    ])

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


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
        )

    connections = await BusinessRepository.get_user_connections(callback.from_user.id)
    has_business = len(connections) > 0

    try:
        await callback.message.delete()
    except Exception:
        pass

    await send_main_menu(callback.message, user, has_business)


@router.callback_query(lambda c: c.data == "savemode_on")
async def savemode_on(callback: CallbackQuery):
    await callback.answer("✅ SAVE MODE включен! Используй /savemode on")


@router.callback_query(lambda c: c.data == "savemode_off")
async def savemode_off(callback: CallbackQuery):
    await callback.answer("❌ SAVE MODE выключен! Используй /savemode off")


@router.message(Command("help"))
async def help_command(message: Message):
    await show_help(message)


@router.message(Command("settings"))
async def settings_command(message: Message):
    await show_settings(message)
