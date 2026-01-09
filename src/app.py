import json
import asyncio
import logging
import warnings
import coloredlogs
from config import config
from aiogram import Bot, Dispatcher
from aiogram.types import PreCheckoutQuery
from handlers import setup_handlers, set_main_menu
from datetime import datetime, timedelta
from functions import delete_client_by_email
from stats_notifier import stats_distribution_task
from database import (
    Session, User, init_db, get_all_users, delete_user_profile, 
    update_user_profile, get_user_stats, cleanup_expired_users,
    get_admin_users, update_user_admin_status
)


warnings.filterwarnings("ignore", category=DeprecationWarning)

# Настройка логирования
def setup_logging():
    """Настройка логирования с сохранением в файл и выводом в консоль"""
    # Создаем логгер
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Формат для логирования
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 1. Файловый обработчик для всех логов
    file_handler = logging.FileHandler('bot.log', encoding='utf-8', mode='a')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(log_format, date_format)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 2. Обработчик для логов платежей
    payments_handler = logging.FileHandler('payments.log', encoding='utf-8', mode='a')
    payments_handler.setLevel(logging.INFO)
    payments_formatter = logging.Formatter(log_format, date_format)
    payments_handler.setFormatter(payments_formatter)
    
    payments_logger = logging.getLogger('payments')
    payments_logger.setLevel(logging.INFO)
    payments_logger.addHandler(payments_handler)
    payments_logger.propagate = False  # Не передаем логи родительскому логгеру
    
    # 3. Консольный обработчик с цветным выводом
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Используем coloredlogs для консоли
    coloredlogs.install(
        level='INFO',
        logger=logger,
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Также настраиваем coloredlogs для aiogram
    coloredlogs.install(
        level='INFO',
        logger=logging.getLogger('aiogram'),
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    return logger

# Инициализируем логирование
logger = setup_logging()

class SubscriptionChecker:
    """Класс для управления проверкой подписок"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        
    async def check_subscriptions(self):
        """Основная функция проверки подписок"""
        while self.running:
            try:
                now = datetime.utcnow()
                users = await get_all_users()
                
                logger.debug(f"🔍 Checking {len(users)} users...")
                
                for user in users:
                    await self._check_user_subscription(user, now)
                    
            except Exception as e:
                logger.error(f"❌ Subscription check error: {e}", exc_info=True)
            
            # Ждем 5 минут перед следующей проверкой
            await asyncio.sleep(300)
    
    async def _check_user_subscription(self, user, now):
        """Проверка подписки конкретного пользователя"""
        # Пропускаем пользователей без даты окончания подписки
        if not user.subscription_end:
            return
        
        # Пропускаем пользователей без VPN профиля
        if not user.vless_profile_data:
            return
        
        try:
            # Парсим данные профиля
            profile_data = json.loads(user.vless_profile_data)
            email = profile_data.get("email", "N/A")
            user_info = f"👤 {user.telegram_id} ({email})"
            
            # =========================
            # 1. УВЕДОМЛЕНИЕ ЗА 24 ЧАСА
            # =========================
            time_to_expire = user.subscription_end - now
            if timedelta(hours=0) <= time_to_expire <= timedelta(hours=24):
                if not user.notified_24h:
                    await self._send_24h_notification(user, email)
            
            # =========================
            # 2. УВЕДОМЛЕНИЕ ЗА 2 ЧАСА
            # =========================
            if timedelta(hours=0) <= time_to_expire <= timedelta(hours=2):
                if not user.notified_2h:
                    await self._send_2h_notification(user, email)
            
            # =========================
            # 3. ПОДПИСКА ИСТЕКЛА
            # =========================
            if user.subscription_end <= now:
                await self._handle_expired_subscription(user, email)
                
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Invalid profile data for user {user.telegram_id}")
        except Exception as e:
            logger.error(f"❌ Error checking user {user.telegram_id}: {e}")
    
    async def _send_24h_notification(self, user, email):
        """Отправить уведомление за 24 часа"""
        try:
            # Уведомление пользователю
            await self.bot.send_message(
                user.telegram_id,
                "⚠️ *Ваша подписка истекает через 24 часа!*\n\n"
                "Продлите подписку, чтобы сохранить доступ к VPN-сервису.\n"
                "Используйте команду /renew для продления подписки",
                parse_mode="Markdown"
            )
            
            # Обновляем флаг в БД
            await self._update_notification_flag(user.telegram_id, 'notified_24h', True)
            logger.info(f"✅ 24h notification sent to {user.telegram_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to send 24h notification to {user.telegram_id}: {e}")
    
    async def _send_2h_notification(self, user, email):
        """Отправить уведомление за 2 часа (пользователю и админам)"""
        try:
            # Уведомление пользователю
            await self.bot.send_message(
                user.telegram_id,
                "⏰ *СРОЧНО! Подписка истекает через 2 часа!*\n\n"
                "Сейчас самое время продлить подписку, "
                "чтобы не потерять доступ к VPN-сервису.\n"
                "Используйте команду /renew для продления подписки.",
                parse_mode="Markdown"
            )
            
            # Уведомление администраторам
            admins = await get_admin_users()
            admin_message = (
                "⏳ *СКОРО ИСТЕКАЕТ ПОДПИСКА*\n\n"
                f"👤 Пользователь: `{user.telegram_id}`\n"
                f"📧 Email: `{email}`\n"
                f"👤 Имя: {user.full_name or 'Не указано'}\n"
                f"⏰ Истекает: `{user.subscription_end}` (через 2 часа)"
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
                "Используйте команду /renew для продления подписки",
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
        """Обновить флаг уведомления в БД"""
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if user:
                setattr(user, flag_name, value)
                session.commit()
    
    async def start(self):
        """Запустить проверку подписок"""
        self.running = True
        asyncio.create_task(self.check_subscriptions())
        logger.info("✅ Subscription checker started")
    
    async def stop(self):
        """Остановить проверку подписок"""
        self.running = False
        logger.info("🛑 Subscription checker stopped")

async def reset_notification_flags():
    """Сброс флагов уведомлений для пользователей с продленной подпиской"""
    while True:
        try:
            now = datetime.utcnow()
            two_hours_ago = now - timedelta(hours=2)
            
            with Session() as session:
                # Находим пользователей, которые продлили подписку
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
                
                # Очистка старых записей (раз в сутки)
                if now.hour == 3:  # В 3 часа ночи
                    cleaned = await cleanup_expired_users()
                    if cleaned > 0:
                        logger.info(f"🧹 Cleaned up {cleaned} expired user records")
        
        except Exception as e:
            logger.error(f"❌ Reset notification flags error: {e}")
        
        # Проверяем раз в 6 часов
        await asyncio.sleep(21600)

async def update_admins_from_config():
    """Обновить администраторов из конфига"""
    try:
        with Session() as session:
            # Сбрасываем всем статус админа
            session.query(User).update({User.is_admin: False})
            
            # Устанавливаем админов из конфига
            for admin_id in config.ADMINS:
                user = session.query(User).filter_by(telegram_id=admin_id).first()
                if user:
                    user.is_admin = True
                else:
                    # Создаем запись для админа, если её нет
                    new_admin = User(
                        telegram_id=admin_id,
                        full_name=f"Admin {admin_id}",
                        is_admin=True,
                        subscription_end=datetime.utcnow() + timedelta(days=365*10)  # 10 лет
                    )
                    session.add(new_admin)
            
            session.commit()
            logger.info(f"✅ Updated {len(config.ADMINS)} admins from config")
    except Exception as e:
        logger.error(f"❌ Failed to update admins: {e}")

async def main():
    """Основная функция запуска бота"""
    # Инициализация бота
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.client.session.aiohttp import AiohttpSession

    async def main():
    # Создаем устойчивую сессию
        session = AiohttpSession(
        timeout=ClientTimeout(
            total=30,      # Общий таймаут 30 секунд
            connect=10,    # Таймаут соединения 10 секунд
            sock_read=25   # Таймаут чтения 25 секунд
        )
    )
    bot = Bot(
        token=config.BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Инициализация проверки подписок
    subscription_checker = SubscriptionChecker(bot)
    
    try:
        # Инициализация базы данных
        await init_db()
        logger.info("✅ Database initialized")
        
        # Обновляем администраторов
        await update_admins_from_config()
        
        # Подключаем хендлеры
        setup_handlers(dp)
        logger.info("✅ Handlers registered")
        
        # Устанавливаем главное меню
        await set_main_menu(bot)
        
        # Обработчик предварительной проверки платежа
        @dp.pre_checkout_query()
        async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
            await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
        
        # Запускаем фоновые задачи
        await subscription_checker.start()
        asyncio.create_task(reset_notification_flags())
        asyncio.create_task(stats_distribution_task(bot))
        
        logger.info("🤖 Bot started successfully!")
        logger.info(f"👑 Admins: {config.ADMINS}")
        
        # Старт поллинга
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.critical(f"❌ Failed to start bot: {e}", exc_info=True)
    finally:
        await subscription_checker.stop()
        await bot.session.close()
        logger.info("👋 Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}", exc_info=True)