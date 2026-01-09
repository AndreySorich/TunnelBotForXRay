# stats_notifier.py
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from database import get_all_users, Session, User
from functions import get_user_stats
import json

logger = logging.getLogger(__name__)

async def send_weekly_stats_to_user(bot: Bot, user):
    """Отправляет статистику трафика пользователю без уведомления"""
    try:
        if not user.vless_profile_data:
            return False
        
        # Парсим данные профиля
        profile_data = json.loads(user.vless_profile_data)
        email = profile_data.get("email")
        
        if not email:
            return False
        
        # Получаем статистику
        stats = await get_user_stats(email)
        
        # Форматируем статистику
        upload_mb = stats.get('upload', 0) / (1024 * 1024)
        download_mb = stats.get('download', 0) / (1024 * 1024)
        
        # Конвертируем в ГБ если нужно
        if upload_mb > 1024:
            upload_str = f"{upload_mb / 1024:.2f} GB"
        else:
            upload_str = f"{upload_mb:.2f} MB"
        
        if download_mb > 1024:
            download_str = f"{download_mb / 1024:.2f} GB"
        else:
            download_str = f"{download_mb:.2f} MB"
        
        # Проверяем статус подписки
        now = datetime.utcnow()
        if user.subscription_end > now:
            days_left = (user.subscription_end - now).days
            status_text = f"📅 Подписка активна\n⏳ Осталось дней: **{days_left}**"
        else:
            status_text = "⚠️ **Подписка истекла**"
        
        # Формируем сообщение
        message = (
            "📊 **Еженедельная статистика трафика**\n\n"
            f"👤 Пользователь: {user.full_name}\n"
            f"🆔 ID: `{user.telegram_id}`\n\n"
            f"{status_text}\n\n"
            "📈 **Использование трафика:**\n"
            f"🔼 Загружено: `{upload_str}`\n"
            f"🔽 Скачано: `{download_str}`\n"
            f"📊 Всего: `{upload_mb + download_mb:.2f} MB`\n\n"
            "Для управления подпиской используйте /menu"
        )
        
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode="Markdown",
            disable_notification=True  # <-- БЕЗ УВЕДОМЛЕНИЯ
        )
        
        logger.info(f"✅ weekly stats sent silently to user {user.telegram_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send stats to user {user.telegram_id}: {e}")
        return False

async def send_weekly_stats_to_all(bot: Bot):
    """Отправляет статистику всем пользователям с активной подпиской"""
    try:
        users = await get_all_users(with_active_subscription=True)
        
        success_count = 0
        failed_count = 0
        
        for user in users:
            try:
                success = await send_weekly_stats_to_user(bot, user)
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                
                # Задержка между отправками чтобы не заблокировали
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Error processing user {user.telegram_id}: {e}")
                failed_count += 1
        
        logger.info(
            f"📊 weekly stats distribution completed: "
            f"✅ {success_count} успешно, ❌ {failed_count} ошибок"
        )
        
        # Отправляем отчет админам
        await notify_admins_about_stats_distribution(bot, success_count, failed_count, len(users))
        
    except Exception as e:
        logger.error(f"❌ weekly stats distribution failed: {e}")

async def notify_admins_about_stats_distribution(bot: Bot, success: int, failed: int, total: int):
    """Уведомляет администраторов о результатах рассылки"""
    from config import config
    
    message = (
        "📊 **Отчет по ежедневной рассылке статистики**\n\n"
        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y')}\n"
        f"👥 Всего пользователей: {total}\n"
        f"✅ Успешно отправлено: {success}\n"
        f"❌ Ошибок отправки: {failed}\n"
        f"📈 Успешность: {(success/total*100):.1f}%"
    )
    
    for admin_id in config.ADMINS:
        try:
            await bot.send_message(
                admin_id,
                message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"❌ Failed to notify admin {admin_id}: {e}")

async def stats_distribution_task(bot: Bot):
    """Фоновая задача для еженедельной рассылки статистики (по пятницам)"""
    while True:
        try:
            now = datetime.now()

            # Пятница = 4
            days_until_friday = (4 - now.weekday()) % 7
            target_date = now + timedelta(days=days_until_friday)

            target_time = target_date.replace(
                hour=20, minute=0, second=0, microsecond=0
            )

            # Если сегодня пятница, но время уже прошло — берем следующую
            if now >= target_time:
                target_time += timedelta(days=7)

            wait_seconds = (target_time - now).total_seconds()

            logger.info(
                f"⏰ Next weekly stats distribution at "
                f"{target_time.strftime('%H:%M %d.%m.%Y')}"
            )

            await asyncio.sleep(wait_seconds)

            logger.info("🚀 Starting weekly stats distribution...")
            await send_weekly_stats_to_all(bot)

        except Exception as e:
            logger.error(f"❌ Stats distribution task error: {e}")
            await asyncio.sleep(3600)
