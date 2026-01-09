<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Aiogram-3.x-green?style=for-the-badge&logo=telegram" alt="Aiogram">
  <img src="https://img.shields.io/badge/XRay--Core-✅-success?style=for-the-badge" alt="XRay Core">
  <img src="https://img.shields.io/badge/Telegram%20Stars-⭐-yellow?style=for-the-badge" alt="Telegram Stars">
  <img src="https://img.shields.io/badge/License-MIT-red?style=for-the-badge" alt="License">
</p>

<h1 align="center">
  📡 TunnelBotForXRay
</h1>
<p align="center">
  <b>Telegram‑бот для управления VPN‑сервисом на основе XRay Core</b><br>
  Полный контроль подписок, оплаты и конфигураций через Telegram
</p>

<p align="center">
  <a href="#-добавленный-функционал">✨ Функционал</a> •
  <a href="#-возможности">💡 Возможности</a> •
  <a href="#-установка">🛠 Установка</a> •
  <a href="#-структура-проекта">📂 Структура</a> •
  <a href="#-команды">📱 Команды</a> •
  <a href="#-админ-панель">🧠 Админ-панель</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/ARosic1991/TunnelBotForXRay?style=social" alt="GitHub Stars">
  <img src="https://img.shields.io/github/forks/ARosic1991/TunnelBotForXRay?style=social" alt="GitHub Forks">
</p>

---

## ✨ Добавленный функционал

<p align="center">
  <i>Расширенная версия на основе <a href="https://github.com/QueenDekim/XRay-bot">XRay-bot</a></i>
</p>

<table>
  <tr>
    <td width="50%" align="center">
      <h3>🎨 Улучшения интерфейса</h3>
      <ul align="left">
        <li><b>Боковое меню</b> – Удобная навигация</li>
        <li><b>Кнопка Help</b> – Прямая связь с поддержкой</li>
        <li><b>Интуитивный дизайн</b> – Улучшен UX/UI</li>
      </ul>
    </td>
    <td width="50%" align="center">
      <h3>🔔 Умные уведомления</h3>
      <ul align="left">
        <li><b>Администратору</b> – О всех событиях</li>
        <li><b>Пользователям</b> – За 24 и 2 часа до конца</li>
        <li><b>Еженедельная аналитика</b> – Отчет по трафику</li>
      </ul>
    </td>
  </tr>
</table>

---

## 💡 Возможности

### 🧑‍💻 Для пользователей
<table>
  <tr>
    <td><b>🚀 VPN Профили</b></td>
    <td>Автоматическое создание VLESS конфигураций</td>
  </tr>
  <tr>
    <td><b>💳 Оплата</b></td>
    <td>Telegram Stars ⭐ или банковский перевод</td>
  </tr>
  <tr>
    <td><b>📱 Кроссплатформенность</b></td>
    <td>Windows, Linux, macOS, iOS, Android</td>
  </tr>
  <tr>
    <td><b>📊 Статистика</b></td>
    <td>Мониторинг трафика в реальном времени</td>
  </tr>
  <tr>
    <td><b>🔔 Уведомления</b></td>
    <td>Автоматические напоминания о подписках</td>
  </tr>
</table>

### 🛠 Для администраторов
<table>
  <tr>
    <td><b>👥 Управление</b></td>
    <td>Полный контроль над пользователями и подписками</td>
  </tr>
  <tr>
    <td><b>📊 Аналитика</b></td>
    <td>Детальная статистика использования</td>
  </tr>
  <tr>
    <td><b>📢 Рассылки</b></td>
    <td>Таргетированные уведомления для групп пользователей</td>
  </tr>
  <tr>
    <td><b>⚙️ Настройки</b></td>
    <td>Гибкая конфигурация цен и периодов подписки</td>
  </tr>
</table>

---

## 🛠 Установка и настройка

### 📦 1. Клонирование репозитория
```bash
git clone https://github.com/AndreySorich/TunnelBotForXRay.git
cd TunnelBotForXRay
```
### 🔧 2. Установка зависимостей
```bash
pip install -r requirements.txt
```
### ⚙️ 3. Настройка конфигурации
Создайте файл `.env` на основе `.env.example`:
```env
# ========= TELEGRAM BOT =========
BOT_TOKEN=your_telegram_bot_token
ADMINS=123456789,987654321

# ========= X-UI API =========
XUI_API_URL=http://your-server.com:54321
XUI_USERNAME=admin
XUI_PASSWORD=your_password
XUI_HOST=vpn.your-domain.com
INBOUND_ID=1

# ========= REALITY (опционально) =========
REALITY_PUBLIC_KEY=your_public_key
REALITY_FINGERPRINT=chrome
REALITY_SNI=example.com
REALITY_SHORT_ID=1234567890
REALITY_SPIDER_X=/

# ========= ПЛАТЕЖИ =========
TINKOFF_PAY_URL=your_tinkoff_payment_link
```
### 🤖 4. Настройка бота через @BotFather
### 🚀 5. Запуск бота
```bash
cd src
python app.py
```
💡 Примечание: База данных создается автоматически при первом запуске
### 📂 Структура проекта
```text
TunnelBotForXRay/
├── src/                          # Исходный код
│   ├── bot.log                   # Основной лог
│   ├── payments.log              # Логи платежей
│   ├── app.py                    # Основной файл запуска
│   ├── config.py                 # Конфигурация бота
│   ├── database.py               # Работа с БД и X-UI API
│   ├── handlers.py               # Обработчики команд
│   ├── notifications.py          # Система уведомлений
│   └── functions.py              # Вспомогательные функции
├── .env.example                  # Пример конфигурации
├── requirements.txt              # Зависимости Python
├── README.md                     # Эта документация
└── logs/                         # Логи работы
```
## 📱 Команды бота
- `/start` Начало работы
- `/menu` Главное меню
- `/renew` Продлить подписку
- `/connect` Получить VPN-конфиг
- `/help` Помощь и поддержка

## 🧠 Админ-панель
```text
┌─────────────────────────────────┐
│ 📊 Административное меню        │
├─────────────────────────────────┤
│ Всего пользователей: 150        │
│ С подпиской: 85                 │
│ Без подписки: 65                │
│ Онлайн: 42 | Офлайн: 43         │
└─────────────────────────────────┘
```
⚙️ Управление
Функция	Назначение
- `+ время`	Добавить время к подписке
- `- время`	Удалить время из подписки
- `📋 Список пользователей`	Просмотр всех пользователей
- `📊 Статистика исп. сети`	Мониторинг трафика
- `📢 Рассылка`	Отправка сообщений
- `🔔 Тест уведомлений`	Проверка системы уведомлений

## 🔧 Технические особенности
💳 Система оплаты

Telegram Stars – встроенная валюта Telegram

Банковский перевод Тенькоф – ручное подтверждение

Автоматическое обновление подписок после оплаты

## 🙏 Благодарности
Основано на проекте <a href="https://github.com/QueenDekim/XRay-bot">XRay-bot</a></i> от QueenDekim

Моим коллегам и друзьям за тестировани   


<p align="center">
  <i>Моя рабочая версия <a href="https://t.me/TunnelBot_bot/">@TunnelBot</a></i>
</p>
