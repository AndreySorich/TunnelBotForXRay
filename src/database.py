from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
import logging
import json

# В handlers.py, database.py, functions.py и других модулях
import logging

# Получаем логгер для текущего модуля
logger = logging.getLogger(__name__)

# Пример использования
logger.info("Сообщение для bot.log и консоли")

# Для платежей используйте специальный логгер
payments_logger = logging.getLogger('payments')
payments_logger.info("Платеж успешен")  # Только в payments.log

# Для ошибок
error_logger = logging.getLogger('errors')
error_logger.error("Критическая ошибка")  # Только в errors.log

Base = declarative_base()





class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    full_name = Column(String)
    username = Column(String)
    registration_date = Column(DateTime, default=datetime.utcnow)
    subscription_end = Column(DateTime, index=True)  # Индекс для быстрого поиска
    vless_profile_id = Column(String)
    vless_profile_data = Column(String)
    is_admin = Column(Boolean, default=False)
    notified_24h = Column(Boolean, default=False)  # Уведомление за 24 часа
    notified_2h = Column(Boolean, default=False)   # Уведомление за 2 часа
    # Новые поля для статистики
    total_upload = Column(Integer, default=0)
    total_download = Column(Integer, default=0)
    last_activity = Column(DateTime, default=datetime.utcnow)

class StaticProfile(Base):
    __tablename__ = 'static_profiles'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    vless_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# Используем SQLite с подключением в память для тестов или файл
engine = create_engine('sqlite:///users.db', echo=False, pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)

async def init_db():
    """Инициализация базы данных"""
    Base.metadata.create_all(engine)
    logger.info("✅ Database tables created")

def get_session():
    """Получение сессии БД"""
    return Session()

async def get_user(telegram_id: int):
    """Получить пользователя по Telegram ID"""
    with Session() as session:
        return session.query(User).filter_by(telegram_id=telegram_id).first()

async def create_user(telegram_id: int, full_name: str, username: str = None, is_admin: bool = False):
    """Создать нового пользователя"""
    with Session() as session:
        # Проверяем, не существует ли уже пользователь
        existing = session.query(User).filter_by(telegram_id=telegram_id).first()
        if existing:
            logger.info(f"ℹ️ User already exists: {telegram_id}")
            return existing
        
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            subscription_end=datetime.utcnow() + timedelta(days=3),  # Пробный период
            is_admin=is_admin,
            last_activity=datetime.utcnow()
        )
        session.add(user)
        session.commit()
        logger.info(f"✅ New user created: {telegram_id} ({full_name})")
        return user

async def delete_user_profile(telegram_id: int):
    """Удалить профиль пользователя (при истечении подписки)"""
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            # Полностью сбрасываем данные профиля
            user.vless_profile_data = None
            user.vless_profile_id = None
            user.notified_24h = False
            user.notified_2h = False
            # subscription_end не меняем - он уже прошедшая дата
            
            session.commit()
            logger.info(f"✅ User profile deleted: {telegram_id}")
            return True
    return False

async def update_user_profile(telegram_id: int, profile_data: dict):
    """Обновить VPN профиль пользователя"""
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.vless_profile_data = json.dumps(profile_data, ensure_ascii=False)
            user.notified_24h = False
            user.notified_2h = False
            user.last_activity = datetime.utcnow()
            session.commit()
            logger.info(f"✅ User profile updated: {telegram_id}")
            return True
    return False

async def update_subscription(telegram_id: int, days: int, reset_notifications: bool = True):
    """Обновляет подписку пользователя"""
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            now = datetime.utcnow()
            
            # Если подписка активна, добавляем к текущей дате окончания
            if user.subscription_end and user.subscription_end > now:
                user.subscription_end += timedelta(days=days)
            else:
                # Если подписка истекла или ее нет, начинаем с текущей даты
                user.subscription_end = now + timedelta(days=days)
            
            # Сбрасываем флаги уведомлений
            if reset_notifications:
                user.notified_24h = False
                user.notified_2h = False
            
            user.last_activity = datetime.utcnow()
            session.commit()
            logger.info(f"✅ Subscription updated for {telegram_id}: +{days} days (until {user.subscription_end})")
            return user.subscription_end
        return None

from sqlalchemy import or_

async def get_all_users(with_active_subscription: bool = None):
    """Получить всех пользователей с фильтрацией по подписке"""
    with Session() as session:
        query = session.query(User)
        now = datetime.utcnow()

        if with_active_subscription is True:
            query = query.filter(
                User.subscription_end.isnot(None),
                User.subscription_end > now,
                User.vless_profile_data.isnot(None)
            )

        elif with_active_subscription is False:
            query = query.filter(
                or_(
                    User.subscription_end.is_(None),
                    User.subscription_end <= now,
                    User.vless_profile_data.is_(None)
                )
            )

        return query.all()


async def get_users_with_expiring_subscription(hours: int = 24):
    """Получить пользователей с истекающей подпиской"""
    with Session() as session:
        now = datetime.utcnow()
        expiration_threshold = now + timedelta(hours=hours)
        
        users = session.query(User).filter(
            User.subscription_end > now,
            User.subscription_end <= expiration_threshold,
            User.vless_profile_data.isnot(None)  # Только у кого есть профиль
        ).all()
        
        return users




async def create_static_profile(name: str, vless_url: str):
    """Создать статический профиль"""
    with Session() as session:
        # Проверяем, нет ли уже профиля с таким именем
        existing = session.query(StaticProfile).filter_by(name=name).first()
        if existing:
            logger.warning(f"⚠️ Static profile already exists: {name}")
            return None
        
        profile = StaticProfile(name=name, vless_url=vless_url)
        session.add(profile)
        session.commit()
        logger.info(f"✅ Static profile created: {name}")
        return profile

async def get_static_profiles():
    """Получить все статические профили"""
    with Session() as session:
        return session.query(StaticProfile).order_by(StaticProfile.created_at.desc()).all()

async def delete_static_profile(profile_id: int):
    """Удалить статический профиль"""
    with Session() as session:
        profile = session.query(StaticProfile).filter_by(id=profile_id).first()
        if profile:
            session.delete(profile)
            session.commit()
            logger.info(f"✅ Static profile deleted: {profile.name}")
            return True
    return False

async def get_user_stats():
    """Получить статистику пользователей"""
    with Session() as session:
        now = datetime.utcnow()
        
        total = session.query(func.count(User.id)).scalar()
        with_sub = session.query(func.count(User.id)).filter(
            User.subscription_end > now
        ).scalar()
        without_sub = total - with_sub
        
        # Пользователи с истекающей подпиской (менее 24 часов)
        expiring_soon = session.query(func.count(User.id)).filter(
            User.subscription_end > now,
            User.subscription_end <= now + timedelta(hours=24)
        ).scalar()
        
        return {
            "total": total,
            "with_active_subscription": with_sub,
            "without_subscription": without_sub,
            "expiring_soon": expiring_soon,
            "trial_users": session.query(func.count(User.id)).filter(
                User.subscription_end > now,
                User.subscription_end <= now + timedelta(days=3)
            ).scalar()
        }

async def update_user_stats(telegram_id: int, upload: int = None, download: int = None):
    """Обновить статистику пользователя"""
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            if upload is not None:
                user.total_upload = upload
            if download is not None:
                user.total_download = download
            user.last_activity = datetime.utcnow()
            session.commit()
            return True
    return False

async def get_admin_users():
    """Получить всех администраторов"""
    with Session() as session:
        return session.query(User).filter_by(is_admin=True).all()

async def update_user_admin_status(telegram_id: int, is_admin: bool):
    """Обновить статус администратора"""
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.is_admin = is_admin
            session.commit()
            logger.info(f"✅ Admin status updated for {telegram_id}: {is_admin}")
            return True
    return False

# В database.py добавьте эти функции перед последней строкой:

from datetime import datetime, timedelta

async def update_subscription(telegram_id: int, months: int, is_admin_action: bool = False):
    """Обновляет подписку пользователя и возвращает новую дату окончания"""
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                logger.error(f"❌ User {telegram_id} not found for subscription update")
                return None
            
            # Определяем текущее время
            now = datetime.utcnow()
            
            # Если подписка еще активна, продлеваем от текущей даты окончания
            if user.subscription_end and user.subscription_end > now:
                new_end = user.subscription_end + timedelta(days=30*months)
            else:
                # Если подписка истекла или ее нет, начинаем с текущего момента
                new_end = now + timedelta(days=30*months)
            
            user.subscription_end = new_end
            
            # Сбрасываем флаги уведомлений при продлении
            user.notified_24h = False
            user.notified_2h = False
            
            session.commit()
            
            # Логируем продление
            logger.info(
                f"✅ Subscription updated for user {telegram_id}: "
                f"+{months} months, new end: {new_end.strftime('%d.%m.%Y %H:%M')}"
            )
            
            # Логируем в payments.log
            payments_logger.info(
                f"SUBSCRIPTION_EXTENDED | "
                f"user_id={telegram_id} | "
                f"months={months} | "
                f"new_end={new_end.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"admin_action={is_admin_action}"
            )
            
            return new_end
            
    except Exception as e:
        logger.error(f"❌ Error updating subscription for user {telegram_id}: {e}")
        return None

async def add_time_to_subscription(telegram_id: int, months: int, days: int = 0, hours: int = 0, minutes: int = 0):
    """Добавляет время к подписке пользователя (для админ-меню)"""
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                logger.error(f"❌ User {telegram_id} not found for adding time")
                return None
            
            # Вычисляем общее количество секунд
            total_seconds = (
                months * 30 * 24 * 60 * 60 +
                days * 24 * 60 * 60 +
                hours * 60 * 60 +
                minutes * 60
            )
            
            now = datetime.utcnow()
            
            # Если подписка активна, добавляем к текущей дате окончания
            if user.subscription_end > now:
                new_end = user.subscription_end + timedelta(seconds=total_seconds)
            else:
                # Если подписка истекла, добавляем к текущему времени
                new_end = now + timedelta(seconds=total_seconds)
            
            user.subscription_end = new_end
            
            # Сбрасываем флаги уведомлений
            user.notified_24h = False
            user.notified_2h = False
            
            session.commit()
            
            # Вычисляем общее количество месяцев для логирования
            total_months = round(total_seconds / (30 * 24 * 60 * 60), 1)
            
            logger.info(
                f"✅ Time added to user {telegram_id}: "
                f"+{months}m {days}d {hours}h {minutes}m "
                f"(total: ~{total_months} months), "
                f"new end: {new_end.strftime('%d.%m.%Y %H:%M')}"
            )
            
            payments_logger.info(
                f"ADMIN_ADDED_TIME | "
                f"user_id={telegram_id} | "
                f"months={months} | days={days} | hours={hours} | minutes={minutes} | "
                f"total_months={total_months} | "
                f"new_end={new_end.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            return new_end
            
    except Exception as e:
        logger.error(f"❌ Error adding time to user {telegram_id}: {e}")
        return None

async def remove_time_from_subscription(telegram_id: int, months: int, days: int = 0, hours: int = 0, minutes: int = 0):
    """Удаляет время из подписки пользователя (для админ-меню)"""
    try:
        with Session() as session:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                logger.error(f"❌ User {telegram_id} not found for removing time")
                return None
            
            # Вычисляем общее количество секунд
            total_seconds = (
                months * 30 * 24 * 60 * 60 +
                days * 24 * 60 * 60 +
                hours * 60 * 60 +
                minutes * 60
            )
            
            # Вычитаем время
            new_end = user.subscription_end - timedelta(seconds=total_seconds)
            
            # Проверяем, чтобы не ушло в прошлое
            now = datetime.utcnow()
            if new_end < now:
                new_end = now
            
            user.subscription_end = new_end
            
            # Если подписка теперь истекла, сбрасываем флаги уведомлений
            if new_end <= now:
                user.notified_24h = False
                user.notified_2h = False
            
            session.commit()
            
            # Вычисляем общее количество месяцев для логирования
            total_months = round(total_seconds / (30 * 24 * 60 * 60), 1)
            
            logger.info(
                f"✅ Time removed from user {telegram_id}: "
                f"-{months}m {days}d {hours}h {minutes}m "
                f"(total: ~{total_months} months), "
                f"new end: {new_end.strftime('%d.%m.%Y %H:%M')}"
            )
            
            payments_logger.info(
                f"ADMIN_REMOVED_TIME | "
                f"user_id={telegram_id} | "
                f"months={months} | days={days} | hours={hours} | minutes={minutes} | "
                f"total_months={total_months} | "
                f"new_end={new_end.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            return new_end
            
    except Exception as e:
        logger.error(f"❌ Error removing time from user {telegram_id}: {e}")
        return None

async def cleanup_expired_users():
    """Очистка устаревших данных (пользователи без подписки и профиля)"""
    with Session() as session:
        month_ago = datetime.utcnow() - timedelta(days=30)
        
        # Находим пользователей без подписки и без профиля более месяца
        expired_users = session.query(User).filter(
            User.subscription_end < month_ago,
            User.vless_profile_data.is_(None),
            User.is_admin == False
        ).all()
        
        deleted_count = 0
        for user in expired_users:
            session.delete(user)
            deleted_count += 1
        
        if deleted_count > 0:
            session.commit()
            logger.info(f"🧹 Cleaned up {deleted_count} expired user records")
        
        return deleted_count