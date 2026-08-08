import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot

from src.config import settings
from src.db.session import async_session
from sqlalchemy import select
from src.db.models import User

logger = logging.getLogger(__name__)


class SubscriptionChecker:
    """Проверяет подписки и отправляет уведомления об окончании"""

    @staticmethod
    async def check_and_notify(bot: Bot):
        """Проверяет подписки и отправляет уведомления"""
        try:
            async with async_session() as session:
                now = datetime.utcnow()
                
                # Находим пользователей с активной подпиской
                users = await session.scalars(
                    select(User).where(
                        User.subscription_until > now,
                        User.subscription_until.isnot(None)
                    )
                )
                users = list(users)
                
                if not users:
                    return
                
                notified_count = 0
                expired_count = 0
                
                for user in users:
                    days_left = (user.subscription_until - now).days
                    
                    # Уведомление за 1 день
                    if days_left == 1:
                        await SubscriptionChecker._notify_user(
                            bot, user,
                            f"⚠️ <b>Подписка истекает завтра!</b>\n\n"
                            f"📅 Ваша подписка SafeSaverX закончится <b>завтра</b>.\n"
                            f"📆 Действует до: <b>{user.subscription_until.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
                            f"💰 Продлите подписку сейчас: /pay\n\n"
                            f"<i>Если не продлить, SAVE MODE и уведомления перестанут работать.</i>"
                        )
                        notified_count += 1
                        logger.info(f"📨 Отправлено уведомление за 1 день пользователю {user.telegram_id}")
                    
                    # Уведомление в день окончания (0 дней)
                    elif days_left == 0:
                        await SubscriptionChecker._notify_user(
                            bot, user,
                            f"⛔ <b>Подписка истекает СЕГОДНЯ!</b>\n\n"
                            f"📅 Ваша подписка SafeSaverX закончится <b>сегодня</b>.\n"
                            f"📆 Действует до: <b>{user.subscription_until.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
                            f"💰 Продлите подписку прямо сейчас: /pay\n\n"
                            f"<i>После истечения подписки SAVE MODE и уведомления отключатся.</i>"
                        )
                        notified_count += 1
                        logger.info(f"📨 Отправлено уведомление в день окончания пользователю {user.telegram_id}")
                
                # Проверяем истекшие подписки
                expired_users = await session.scalars(
                    select(User).where(
                        User.subscription_until <= now,
                        User.subscription_until.isnot(None),
                        User.subscription_until > now - timedelta(days=1)  # Проверяем только те, что истекли за последние 24 часа
                    )
                )
                expired_users = list(expired_users)
                
                for user in expired_users:
                    # Проверяем, не отправляли ли уже уведомление об истечении
                    if not hasattr(user, '_expired_notified'):
                        await SubscriptionChecker._notify_user(
                            bot, user,
                            f"⛔ <b>Подписка истекла!</b>\n\n"
                            f"📅 Ваша подписка SafeSaverX закончилась.\n"
                            f"📆 Действовала до: <b>{user.subscription_until.strftime('%d.%m.%Y %H:%M') if user.subscription_until else '—'}</b>\n\n"
                            f"💰 Продлите подписку сейчас: /pay\n\n"
                            f"<i>SAVE MODE и уведомления отключены до продления подписки.</i>"
                        )
                        expired_count += 1
                        logger.info(f"📨 Отправлено уведомление об истечении пользователю {user.telegram_id}")
                
                if notified_count > 0 or expired_count > 0:
                    logger.info(f"✅ Отправлено уведомлений: {notified_count} о скором окончании, {expired_count} об истечении")
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки подписок: {e}")

    @staticmethod
    async def _notify_user(bot: Bot, user: User, text: str):
        """Отправляет уведомление пользователю"""
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление пользователю {user.telegram_id}: {e}")


async def subscription_checker_loop(bot: Bot):
    """Фоновый цикл проверки подписок (запускается раз в час)"""
    logger.info("🔄 Запущен фоновый сервис проверки подписок")
    
    while True:
        try:
            await SubscriptionChecker.check_and_notify(bot)
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле проверки подписок: {e}")
        
        # Проверяем раз в час
        await asyncio.sleep(3600)