# notifications.py
import logging
from datetime import datetime
from typing import Optional
from aiogram import Bot
from database import get_user
from config import config

logger = logging.getLogger(__name__)

async def send_subscription_extended_notification(
    bot: Bot, 
    telegram_id: int, 
    months: int, 
    new_end_date: datetime,
    is_admin_action: bool = False
):
    """Отправляет уведомление пользователю о продлении подписки"""
    try:
        user = await get_user(telegram_id)
        if not user:
            logger.warning(f"⚠️ Cannot send notification: user {telegram_id} not found")
            return False
        
        # Форматируем дату окончания
        end_date_str = new_end_date.strftime("%d.%m.%Y %H:%M")
        
        # Формируем сообщение в зависимости от типа действия
        suffix = "месяц" if months == 1 else "месяца" if months in (2, 3, 4) else "месяцев"
        
        if is_admin_action:
            message_text = (
                "👑 *Администратор продлил вашу подпичку!*\n\n"
                f"📅 **Продлено на:** {months} {suffix}\n"
                f"📅 **Новая дата окончания:** {end_date_str}\n\n"
                "✅ VPN-сервис продолжит работать без перерывов.\n"
                "Спасибо за использование нашего сервиса! 🚀"
            )
        else:
            message_text = (
                "🎉 *Ваша подписка успешно продлена!*\n\n"
                f"📅 **Продлено на:** {months} {suffix}\n"
                f"📅 **Новая дата окончания:** {end_date_str}\n\n"
                "✅ VPN-сервис продолжит работать без перерывов.\n"
                "Спасибо за использование нашего сервиса! 🚀"
            )
        
        await bot.send_message(
            chat_id=telegram_id,
            text=message_text,
            parse_mode="Markdown"
        )
        
        logger.info(f"✅ Subscription extended notification sent to {telegram_id}")
        payments_logger = logging.getLogger('payments')
        payments_logger.info(
            f"SUBSCRIPTION_NOTIFICATION_SENT | "
            f"user_id={telegram_id} | "
            f"months={months} | "
            f"end_date={end_date_str}"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send subscription notification to {telegram_id}: {e}")
        return False

async def notify_admins_about_payment(
    bot: Bot,
    telegram_id: int,
    amount: float,
    months: int,
    payment_method: str = "Тинькофф"
):
    """Уведомляет администраторов об оплате"""
    try:
        user = await get_user(telegram_id)
        if not user:
            logger.warning(f"⚠️ Cannot notify admins: user {telegram_id} not found")
            return False
        
        suffix = "месяц" if months == 1 else "месяца" if months in (2, 3, 4) else "месяцев"
        
        admin_message = (
            "💰 *НОВАЯ ОПЛАТА*\n\n"
            f"👤 **Пользователь:** {user.full_name}\n"
            f"🆔 **Telegram ID:** `{telegram_id}`\n"
            f"📧 **Имя:** {user.full_name}\n"
            f"📅 **Период:** {months} {suffix}\n"
            f"💳 **Сумма:** {amount} ₽\n"
            f"🏦 **Способ оплаты:** {payment_method}\n"
            f"🕐 **Время:** {datetime.now().strftime('%H:%M %d.%m.%Y')}"
        )
        
        success_count = 0
        for admin_id in config.ADMINS:
            try:
                await bot.send_message(
                    admin_id,
                    admin_message,
                    parse_mode="Markdown"
                )
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to send admin notification to {admin_id}: {e}")
        
        logger.info(f"✅ Admin notifications sent ({success_count}/{len(config.ADMINS)})")
        return success_count > 0
        
    except Exception as e:
        logger.error(f"❌ Failed to send admin notifications: {e}")
        return False

async def send_test_notification(bot: Bot, telegram_id: int):
    """Отправляет тестовое уведомление"""
    try:
        await bot.send_message(
            telegram_id,
            "🔔 *Тестовое уведомление*\n\n"
            "Если вы видите это сообщение, система уведомлений работает корректно! ✅",
            parse_mode="Markdown"
        )
        logger.info(f"✅ Test notification sent to {telegram_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send test notification: {e}")
        return False