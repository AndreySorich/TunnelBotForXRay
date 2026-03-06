import json
import asyncio
import logging
import warnings
import coloredlogs
import pytz
from config import config
from aiogram import Bot, Dispatcher
from aiogram.types import PreCheckoutQuery
from handlers import setup_handlers, set_main_menu
from datetime import datetime, timedelta, timezone
from functions import delete_client_by_email
from stats_notifier import stats_distribution_task
from database import (
    Session, User, init_db, get_all_users, delete_user_profile,
    update_user_profile, cleanup_expired_users, get_admin_users
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


warnings.filterwarnings("ignore", category=DeprecationWarning)

# =========================
# Настройка логирования
# =========================
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    file_handler = logging.FileHandler('bot.log', encoding='utf-8', mode='a')
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    coloredlogs.install(level='INFO', logger=logger,
                        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%H:%M:%S')
    return logger

logger = setup_logging()

# Московское время
MSK = pytz.timezone("Europe/Moscow")

# =========================
# Конвертация всех naive дат в MSK
# =========================
async def migrate_subscription_end_to_msk():
    with Session() as session:
        users = session.query(User).all()
        updated_count = 0
        for user in users:
            if user.subscription_end and user.subscription_end.tzinfo is None:
                user.subscription_end = MSK.localize(user.subscription_end)
                updated_count += 1
        if updated_count > 0:
            session.commit()
            logger.info(f"✅ Migrated {updated_count} subscription_end to MSK")
        return updated_count

# =========================
# Класс проверки подписок
# =========================
class SubscriptionChecker:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False

    async def check_subscriptions(self):
        while self.running:
            try:
                now = datetime.now(MSK)
                users = await get_all_users()
                logger.debug(f"🔍 Checking {len(users)} users...")
                for user in users:
                    await self._check_user_subscription(user, now)
            except Exception as e:
                logger.error(f"❌ Subscription check error: {e}", exc_info=True)
            await asyncio.sleep(300)  # Проверяем каждые 5 минут

    async def _check_user_subscription(self, user, now):
        if not user.subscription_end or not user.vless_profile_data:
            return

        # Приводим subscription_end к aware datetime в MSK
        subscription_end = user.subscription_end
        if subscription_end.tzinfo is None:
            subscription_end = MSK.localize(subscription_end)

        try:
            profile_data = json.loads(user.vless_profile_data)
            email = profile_data.get("email", "N/A")

            time_to_expire = subscription_end - now

            # 24 часа
            if timedelta(0) <= time_to_expire <= timedelta(hours=24):
                if not user.notified_24h:
                    await self._send_24h_notification(user, email)

            # 2 часа
            if timedelta(0) <= time_to_expire <= timedelta(hours=2):
                if not user.notified_2h:
                    await self._send_2h_notification(user, email)

            # Подписка истекла
            if subscription_end <= now:
                await self._handle_expired_subscription(user, email)

        except json.JSONDecodeError:
            logger.warning(f"⚠️ Invalid profile data for user {user.telegram_id}")
        except Exception as e:
            logger.error(f"❌ Error checking user {user.telegram_id}: {e}")

    async def _send_24h_notification(self, user, email):
        try:
            # Создаем клавиатуру с кнопкой продления
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="renew")]
            ])
            
            await self.bot.send_message(
                user.telegram_id,
                "⚠️ *Ваша подписка истекает через 24 часа!*\n\n"
                "Продлите подписку, чтобы сохранить доступ к VPN.\n"
                "Нажмите кнопку ниже для продления:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await self._update_notification_flag(user.telegram_id, 'notified_24h', True)
            logger.info(f"✅ 24h notification sent to {user.telegram_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send 24h notification to {user.telegram_id}: {e}")

    async def _send_2h_notification(self, user, email):
        """Отправить уведомление за 2 часа (пользователю и админам)"""
        try:
            # Создаем клавиатуру с кнопкой продления
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Срочно продлить!", callback_data="renew")]
            ])
            
            # Уведомление пользователю
            await self.bot.send_message(
                user.telegram_id,
                "⏰ *Внимание! Подписка истекает через 2 часа!*\n\n"
                "Сейчас самое время продлить подписку, "
                "чтобы не потерять доступ к VPN-сервису.\n"
                "Нажмите кнопку ниже для продления:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            # Уведомление администраторам
            admins = await get_admin_users()
            admin_message = (
                "⏳ *СКОРО ИСТЕКАЕТ ПОДПИСКА*\n\n"
                f"👤 Пользователь: `{user.telegram_id}`\n"
                f"📧 Email: `{email}`\n"
                f"👤 Имя: {user.full_name or 'Не указано'}\n"
                f"⏰ Истекает: `{user.subscription_end}` (через 2 часа)\n\n"
                f"Была отправлена кнопка продления"
            )
            
            for admin in admins:
                try:
                    await self.bot.send_message(
                        admin.telegram_id,
                        admin_message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to notify admin {admin.telegram_id}: {e}")
            
            # Обновляем флаг в БД
            await self._update_notification_flag(user.telegram_id, 'notified_2h', True)
            logger.info(f"✅ 2h notifications sent for {user.telegram_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to send 2h notification to {user.telegram_id}: {e}")
    
    async def _handle_expired_subscription(self, user, email):
        """Обработка истекшей подписки"""
        try:
            # Удаляем клиента из XUI
            if email != "N/A":
                success = await delete_client_by_email(email)
                if not success:
                    logger.warning(f"⚠️ Failed to delete client {email} from XUI")
            
            # Удаляем профиль из БД
            await delete_user_profile(user.telegram_id)
            
            # Уведомление пользователю
            await self.bot.send_message(
                user.telegram_id,
                "❌ *Ваша подписка истекла*\n\n"
                "VPN-профиль был отключён.\n"
                "Используйте команду */renew* для продления подписки",
                parse_mode="Markdown"
            )
            
            # Уведомление администраторам
            admins = await get_admin_users()
            admin_message = (
                "📉 *ПОДПИСКА ЗАВЕРШЕНА*\n\n"
                f"👤 Пользователь: `{user.telegram_id}`\n"
                f"📧 Email: `{email}`\n"
                f"👤 Имя: {user.full_name or 'Не указано'}\n"
                f"⏰ Окончание: `{user.subscription_end}`\n"
                "🧹 Клиент удалён из XUI"
            )
            
            for admin in admins:
                try:
                    await self.bot.send_message(
                        admin.telegram_id,
                        admin_message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to notify admin about expired sub: {e}")
            
            logger.info(f"✅ Subscription ended for {user.telegram_id} ({email})")
            
        except Exception as e:
            logger.error(f"❌ Error handling expired subscription for {user.telegram_id}: {e}")

    async def _update_notification_flag(self, telegram_id: int, flag_name: str, value: bool):
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if user:
                setattr(user, flag_name, value)
                session.commit()

    async def start(self):
        self.running = True
        asyncio.create_task(self.check_subscriptions())
        logger.info("✅ Subscription checker started")

    async def stop(self):
        self.running = False
        logger.info("🛑 Subscription checker stopped")


# =========================
# Фоновая задача сброса уведомлений
# =========================
async def reset_notification_flags():
    while True:
        try:
            now = datetime.now(MSK)
            with Session() as session:
                users_to_reset = session.query(User).filter(
                    User.subscription_end > now + timedelta(hours=24),
                    (User.notified_24h == True) | (User.notified_2h == True)
                ).all()
                reset_count = 0
                for user in users_to_reset:
                    user.notified_24h = False
                    user.notified_2h = False
                    reset_count += 1
                if reset_count > 0:
                    session.commit()
                    logger.info(f"✅ Reset notification flags for {reset_count} users")

                # Очистка старых пользователей в 3:00 МСК
                if now.hour == 3:
                    cleaned = await cleanup_expired_users()
                    if cleaned > 0:
                        logger.info(f"🧹 Cleaned up {cleaned} expired users")

        except Exception as e:
            logger.error(f"❌ Reset notification flags error: {e}")

        await asyncio.sleep(21600)  # каждые 6 часов

# =========================
# Обновление админов
# =========================
async def update_admins_from_config():
    try:
        with Session() as session:
            session.query(User).update({User.is_admin: False})
            for admin_id in config.ADMINS:
                user = session.query(User).filter_by(telegram_id=admin_id).first()
                if user:
                    user.is_admin = True
                else:
                    new_admin = User(
                        telegram_id=admin_id,
                        full_name=f"Admin {admin_id}",
                        is_admin=True,
                        subscription_end=datetime.now(MSK) + timedelta(days=365*10)
                    )
                    session.add(new_admin)
            session.commit()
            logger.info(f"✅ Updated {len(config.ADMINS)} admins from config")
    except Exception as e:
        logger.error(f"❌ Failed to update admins: {e}")


# =========================
# Main
# =========================
async def main():
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiohttp import ClientTimeout

    # Создаем сессию
    session = AiohttpSession(timeout=ClientTimeout(total=30, connect=10, sock_read=25))
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    # Инициализация
    subscription_checker = SubscriptionChecker(bot)
    await init_db()
    await migrate_subscription_end_to_msk()
    await update_admins_from_config()
    setup_handlers(dp)
    await set_main_menu(bot)

    # Предварительная проверка платежа
    @dp.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    # Запуск фоновых задач
    await subscription_checker.start()
    asyncio.create_task(reset_notification_flags())
    asyncio.create_task(stats_distribution_task(bot))

    logger.info("🤖 Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}", exc_info=True)
