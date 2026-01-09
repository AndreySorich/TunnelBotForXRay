import asyncio
import sqlite3
from datetime import datetime, timedelta

def fix_all_subscriptions():
    """Исправляет все даты окончания подписки в базе"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    print("🔧 Исправление временных меток в базе данных...")
    
    # 1. Показываем текущие данные
    cursor.execute("SELECT telegram_id, full_name, subscription_end FROM users")
    users = cursor.fetchall()
    
    for user in users:
        tg_id, name, sub_end = user
        if sub_end:
            # Конвертируем строку в datetime
            old_date = datetime.fromisoformat(sub_end.replace('Z', ''))
            new_date = old_date + timedelta(hours=3)
            
            print(f"👤 {tg_id} ({name}):")
            print(f"   Было: {old_date}")
            print(f"   Стало: {new_date}")
            
            # Обновляем в базе
            cursor.execute(
                "UPDATE users SET subscription_end = ? WHERE telegram_id = ?",
                (new_date.isoformat(), tg_id)
            )
    
    conn.commit()
    conn.close()
    print("\n✅ Все даты исправлены!")

async def force_check_user(user_id: int):
    """Принудительная проверка и отключение пользователя"""
    from database import Session, User
    from functions import delete_client_by_email, delete_user_profile
    import json
    
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            print(f"❌ Пользователь {user_id} не найден")
            return
        
        print(f"👤 Пользователь: {user.full_name} (ID: {user.telegram_id})")
        print(f"📅 Окончание подписки: {user.subscription_end}")
        print(f"⏰ Текущее время: {datetime.utcnow()}")
        
        # Проверяем по новой логике (вычитаем 3 часа)
        subscription_end_utc = user.subscription_end - timedelta(hours=3)
        
        if subscription_end_utc <= datetime.utcnow():
            print("✅ Подписка ИСТЕКЛА (по UTC)")
            
            if user.vless_profile_data:
                profile = json.loads(user.vless_profile_data)
                email = profile.get("email")
                
                if email:
                    print(f"📧 Удаляем из XUI: {email}")
                    success = await delete_client_by_email(email)
                    if success:
                        await delete_user_profile(user.telegram_id)
                        print("✅ Пользователь отключен")
                    else:
                        print("❌ Ошибка удаления из XUI")
            else:
                print("ℹ️ Нет VPN профиля")
        else:
            print("❌ Подписка еще активна (по UTC)")
            time_left = subscription_end_utc - datetime.utcnow()
            print(f"⏳ Осталось: {time_left}")

if __name__ == "__main__":
    # Сначала исправляем базу данных
    fix_all_subscriptions()
    
    # Затем принудительно проверяем проблемного пользователя
    asyncio.run(force_check_user(424431134))