import sqlite3
from datetime import datetime

def fix_all_dates():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # 1. Показываем проблемные записи
    print("🔍 Поиск проблемных записей...")
    cursor.execute("""
        SELECT id, telegram_id, 
               typeof(subscription_end) as sub_type, 
               typeof(registration_date) as reg_type,
               typeof(last_activity) as act_type,
               subscription_end, registration_date, last_activity
        FROM users 
        WHERE typeof(subscription_end) != 'text' 
           OR typeof(registration_date) != 'text'
           OR typeof(last_activity) != 'text'
           OR subscription_end IS NULL
           OR registration_date IS NULL
           OR last_activity IS NULL
    """)
    
    problem_records = cursor.fetchall()
    
    if not problem_records:
        print("✅ Нет проблемных записей")
        return
    
    print(f"⚠️ Найдено {len(problem_records)} проблемных записей")
    
    # 2. Функция для исправления даты
    def fix_date_value(date_value, default_days=0):
        if date_value is None:
            result = datetime.now()
        elif isinstance(date_value, (int, float)):
            # Если это число (timestamp)
            result = datetime.fromtimestamp(date_value)
        elif isinstance(date_value, str):
            try:
                # Пробуем разные форматы
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d']:
                    try:
                        result = datetime.strptime(date_value, fmt)
                        break
                    except:
                        continue
                else:
                    result = datetime.now()
            except:
                result = datetime.now()
        else:
            result = datetime.now()
        
        if default_days > 0:
            result = result.replace(day=result.day + default_days)
        
        return result.strftime('%Y-%m-%d %H:%M:%S')
    
    # 3. Исправляем каждую запись
    fixed_count = 0
    for record in problem_records:
        id, tg_id, sub_type, reg_type, act_type, sub_end, reg_date, last_act = record
        
        # Исправляем даты
        new_sub_end = fix_date_value(sub_end, 3)  # +3 дня по умолчанию
        new_reg_date = fix_date_value(reg_date)
        new_last_act = fix_date_value(last_act)
        
        # Обновляем запись
        cursor.execute("""
            UPDATE users 
            SET subscription_end = ?, 
                registration_date = ?, 
                last_activity = ?
            WHERE id = ?
        """, (new_sub_end, new_reg_date, new_last_act, id))
        
        fixed_count += 1
        
        # Выводим информацию о исправлении
        print(f"🔄 Исправлена запись #{id} (user {tg_id}):")
        print(f"   subscription_end: {sub_end} ({sub_type}) -> {new_sub_end}")
        print(f"   registration_date: {reg_date} ({reg_type}) -> {new_reg_date}")
        print(f"   last_activity: {last_act} ({act_type}) -> {new_last_act}")
        print()
    
    # 4. Сохраняем изменения
    conn.commit()
    
    # 5. Проверяем результат
    cursor.execute("""
        SELECT COUNT(*) as problem_count 
        FROM users 
        WHERE typeof(subscription_end) != 'text' 
           OR typeof(registration_date) != 'text'
           OR typeof(last_activity) != 'text'
    """)
    
    remaining_problems = cursor.fetchone()[0]
    
    if remaining_problems == 0:
        print(f"✅ Успешно исправлено {fixed_count} записей. Все данные корректны.")
    else:
        print(f"⚠️ Осталось {remaining_problems} проблемных записей")
    
    # 6. Показываем несколько записей для проверки
    cursor.execute("SELECT id, telegram_id, subscription_end FROM users LIMIT 5")
    sample = cursor.fetchall()
    print("\n📋 Пример исправленных записей:")
    for row in sample:
        print(f"   ID {row[0]}, User {row[1]}, Subscription: {row[2]}")
    
    conn.close()

if __name__ == "__main__":
    fix_all_dates()