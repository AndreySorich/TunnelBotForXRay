import asyncio
import logging
import json
from datetime import datetime, timedelta
from aiogram import Dispatcher, Router, F, Bot
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import config
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import LabeledPrice
class HelpState(StatesGroup):
    waiting_for_message = State()
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
import aiohttp
from aiogram.types import Message
from database import (
    StaticProfile, get_user, create_user, update_subscription, 
    add_time_to_subscription, remove_time_from_subscription,
    get_all_users, create_static_profile, get_static_profiles, 
    User, Session, get_user_stats as db_user_stats,
    get_admin_users
)
from functions import create_vless_profile, delete_client_by_email, generate_vless_url, get_user_stats, create_static_client, get_global_stats, get_online_users
from notifications import send_subscription_extended_notification, send_test_notification

#логируем 
from logging.handlers import RotatingFileHandler
import os



# Получаем логгер для текущего модуля
logger = logging.getLogger(__name__)

# Для платежей используйте специальный логгер
payments_logger = logging.getLogger('payments')

from aiogram.types import BotCommand

# Устанавливаем главное меню Telegram
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats
import logging

logger = logging.getLogger(__name__)


async def set_main_menu(bot: Bot) -> None:
    commands = [
        BotCommand(command="menu", description="📱 Меню"),
        BotCommand(command="renew", description="💳 Продлить подписку"),
        BotCommand(command="connect", description="🔗 Подключить VPN"),
        BotCommand(command="help", description="❓ Помощь"),
    ]

    # Вариант A: Попробуйте установить для всех scope'ов
    try:
        # 1. Для приватных чатов (основной вариант)
        await bot.set_my_commands(
            commands=commands,
            scope=BotCommandScopeAllPrivateChats(),
            language_code="ru"
        )
        
        # 2. И для default тоже (чтобы точно отображалось)
        await bot.set_my_commands(
            commands=commands,
            scope=BotCommandScopeDefault(),
            language_code="ru"
        )
        
        logger.info("✅ Команды установлены для всех scope'ов")
        
    except Exception as e:
        logger.error(f"❌ Ошибка установки команд: {e}")
    
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

payment_logger = logging.getLogger("payments")
payment_logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    filename=os.path.join(LOG_DIR, "payments.log"),
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3,
    encoding="utf-8"
)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)
handler.setFormatter(formatter)

payment_logger.addHandler(handler)
#логируем

router = Router()

MAX_MESSAGE_LENGTH = 4096

from datetime import datetime
import pytz

MSK = pytz.timezone("Europe/Moscow")

def check_subscription_status(user):
    """
    Проверяет статус подписки с учетом Московского времени
    Возвращает: ("Активна", formatted_date) или ("Истекла", "Истекла")
    """
    if not user or not user.subscription_end:
        return "Истекла", "Истекла"
    
    # Текущее время в MSK
    now_msk = datetime.now(MSK)
    
    # Если subscription_end naive, приводим к MSK
    if user.subscription_end.tzinfo is None:
        subscription_end_msk = MSK.localize(user.subscription_end)
    else:
        subscription_end_msk = user.subscription_end.astimezone(MSK)
    
    # Проверяем статус
    if subscription_end_msk > now_msk:
        # Форматируем дату окончания
        expire_date = subscription_end_msk.strftime("%d-%m-%Y %H:%M")
        return "Активна", expire_date
    else:
        return "Истекла", "Истекла"


# ------------------------------
# FakeCallback для имитации CallbackQuery из Message
# ------------------------------
class FakeCallback:
    def __init__(self, message: Message, data: str):
        self.message = message
        self.from_user = message.from_user
        self.data = data

    async def answer(self, *args, **kwargs):
        # Пустая заглушка, т.к. в callback.answer() ничего не нужно для команд
        pass

# ------------------------------
# Обработчик кнопки "Продлить подписку" из уведомлений
# ------------------------------
@router.callback_query(F.data == "renew")
async def renew_callback(callback: CallbackQuery):
    """Обработка кнопки продления из уведомлений"""
    await callback.answer("Переходим к продлению...")
    
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.message.answer("Сначала запустите бота командой /start")
        return

    # Используем ту же самую клавиатуру, что и в команде /renew
    builder = build_subscription_keyboard(back_callback="back_to_menu")
    
    now = datetime.utcnow()
    
    if user.subscription_end > now:
        days_left = (user.subscription_end - now).days
        text = (
            f"📅 Ваша подписка **активна**\n"
            f"⏳ Осталось дней: **{days_left}**\n"
            f"📅 Истекает: **{user.subscription_end:%d.%m.%Y}**\n\n"
            "💵 **Выберите период продления:**"
        )
    else:
        text = (
            "⚠️ **Ваша подписка истекла**\n\n"
            "💵 **Выберите период для активации:**"
        )
    
    # Отправляем новое сообщение с клавиатурой
    await callback.message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
# ------------------------------
# Команда /renew
# ------------------------------
@router.message(Command("renew"))
async def renew_cmd(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return

    builder = build_subscription_keyboard(back_callback="back_to_menu")

    now = datetime.utcnow()

    if user.subscription_end > now:
        days_left = (user.subscription_end - now).days
        text = (
            f"📅 Ваша подписка **активна**\n"
            f"⏳ Осталось дней: **{days_left}**\n"
            f"📅 Истекает: **{user.subscription_end:%d.%m.%Y}**\n\n"
            "💵 **Выберите период продления:**"
        )
    else:
        text = (
            "⚠️ **Ваша подписка истекла**\n\n"
            "💵 **Выберите период для активации:**"
        )

    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

#### подписка 
def build_subscription_keyboard(back_callback: str):
    builder = InlineKeyboardBuilder()

    for months in sorted(config.PRICES.keys()):
        rub_price = config.calculate_price(months)
        stars_price = config.STARS_PRICES.get(months)

        price_info = config.PRICES[months]
        discount_text = (
            f" (-{price_info['discount_percent']}%)"
            if price_info["discount_percent"] > 0
            else ""
        )

        button_text = (
            f"{months} мес. — "
            f"{rub_price} ₽{discount_text} / "
            f"{stars_price} ⭐"
        )

        builder.button(
            text=button_text,
            callback_data=f"choose_pay_{months}"
        )

    builder.button(text="⬅️ Назад", callback_data=back_callback)
    builder.adjust(1)

    return builder


# ------------------------------
# Команда /connect
# ------------------------------
@router.message(Command("connect"))
async def connect_cmd(message: Message):
    """
    Прямой вызов функции подключения VPN
    """
    import pytz
    from datetime import datetime
    
    MSK = pytz.timezone("Europe/Moscow")
    
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите бота командой /start")
        return
    
    # 1. ПРОВЕРКА СТАТУСА ПОДПИСКИ С MSK
    # Если нет даты окончания подписки
    if not user.subscription_end:
        builder = InlineKeyboardBuilder()
        builder.button(text="💵 Купить подписку", callback_data="renew_sub")
        builder.button(text="⬅️ В меню", callback_data="back_to_menu")
        builder.adjust(1)
        
        await message.answer(
            "❌ <b>Нет активной подписки</b>\n\n"
            "У вас нет активной подписки на VPN.\n"
            "Для подключения необходимо приобрести подписку.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return
    
    # Текущее время в MSK
    now_msk = datetime.now(MSK)
    
    # Приводим subscription_end к MSK если нужно
    if user.subscription_end.tzinfo is None:
        subscription_end_msk = MSK.localize(user.subscription_end)
    else:
        subscription_end_msk = user.subscription_end.astimezone(MSK)
    
    # Проверяем истекла ли подписка
    if subscription_end_msk <= now_msk:
        # Если есть профиль в XUI - удаляем его
        if user.vless_profile_data:
            try:
                profile_data = safe_json_loads(user.vless_profile_data, default={})
                email = profile_data.get("email")
                if email and email != "N/A":
                    await delete_client_by_email(email)
                    logger.info(f"🧹 Удален профиль истекшей подписки через /connect: {email}")
                    
                    # Обновляем БД - удаляем данные профиля
                    with Session() as session:
                        db_user = session.query(User).filter_by(
                            telegram_id=user.telegram_id
                        ).first()
                        if db_user:
                            db_user.vless_profile_data = None
                            session.commit()
            except Exception as e:
                logger.error(f"Ошибка при удалении профиля: {e}")
        
        # Показываем сообщение об истекшей подписке
        expire_date = subscription_end_msk.strftime("%d-%m-%Y %H:%M")
        builder = InlineKeyboardBuilder()
        builder.button(text="💵 Продлить подписку", callback_data="renew_sub")
        builder.button(text="⬅️ В меню", callback_data="back_to_menu")
        builder.adjust(1)
        
        await message.answer(
            f"❌ <b>Подписка истекла!</b>\n\n"
            f"Дата окончания: {expire_date}\n"
            f"Для восстановления доступа к VPN продлите подписку.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return
    
    # 2. ПОДПИСКА АКТИВНА - СОЗДАЕМ/ПОКАЗЫВАЕМ ПРОФИЛЬ
    if not user.vless_profile_data:
        # Создаем новый профиль
        msg = await message.answer("⚙️ Создаем ваш VPN профиль...")
        profile_data = await create_vless_profile(user.telegram_id)
        
        if not profile_data:
            await msg.edit_text("🛑 Ошибка при создании профиля. Попробуйте позже.")
            return
        
        # Сохраняем профиль в БД
        with Session() as session:
            db_user = session.query(User).filter_by(telegram_id=user.telegram_id).first()
            if db_user:
                db_user.vless_profile_data = json.dumps(profile_data)
                session.commit()
                logger.info(f"✅ Создан профиль через /connect для {user.telegram_id}")
        
        # Уведомление админов
        for admin_id in config.ADMINS:
            try:
                await message.bot.send_message(
                    admin_id,
                    "🟢 *Создан новый VPN-клиент (через /connect)*\n\n"
                    f"👤 Telegram ID: `{user.telegram_id}`\n"
                    f"👤 Telegram User: `{user.full_name}`\n"
                    f"📧 Email: `{profile_data['email']}`\n"
                    f"🌐 Inbound: `{profile_data['remark']}`\n"
                    f"🔐 Security: `{profile_data['security']}`\n"
                    f"⏰ Подписка до: `{subscription_end_msk.strftime('%d.%m.%Y %H:%M')}`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"⚠️ Admin notify error ({admin_id}): {e}")
        
        # Обновляем данные пользователя
        user = await get_user(user.telegram_id)
    
    # 3. ПОЛУЧАЕМ И ПОКАЗЫВАЕМ ПРОФИЛЬ
    profile_data = safe_json_loads(user.vless_profile_data, default={})
    if not profile_data:
        await message.answer("❌ Ошибка чтения данных профиля. Попробуйте создать профиль заново.")
        return
    
    # Генерируем ссылку
    vless_url = generate_vless_url(profile_data)
    
    # Рассчитываем сколько осталось дней
    days_left = (subscription_end_msk - now_msk).days
    
    text = (
        f"🎉 <b>Ваш VPN профиль!</b>\n\n"
        f"📅 <b>Подписка активна</b> (осталось {days_left} дней)\n"
        f"⏰ Действует до: {subscription_end_msk.strftime('%d.%m.%Y %H:%M')}\n\n"
        "ℹ️ <b>Инструкция по подключению:</b>\n"
        "1. Скачайте приложение для вашей платформы\n"
        "2. Скопируйте эту ссылку и импортируйте в приложение:\n"
        f"<pre>{vless_url}</pre>\n\n"
        "3. Активируйте соединение в приложении."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text='🖥️ Windows [V2RayN]', url='https://github.com/2dust/v2rayN/releases/download/7.13.8/v2rayN-windows-64-desktop.zip')
    builder.button(text='🐧 Linux [NekoBox]', url='https://github.com/MatsuriDayo/nekoray/releases/download/4.0.1/nekoray-4.0.1-2024-12-12-debian-x64.deb')
    builder.button(text='🍎 Mac [V2RayU]', url='https://github.com/yanue/V2rayU/releases/download/v4.2.6/V2rayU-64.dmg')
    builder.button(text='🍏 iOS [V2RayTun]', url='https://apps.apple.com/ru/app/v2raytun/id6476628951')
    builder.button(text='🤖 Android [V2RayNG]', url='https://github.com/2dust/v2rayNG/releases/download/1.10.16/v2rayNG_1.10.16_arm64-v8a.apk')
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    builder.adjust(2, 2, 1, 1)
    
    # Если мы создавали профиль - редактируем сообщение
    if 'msg' in locals():
        await msg.edit_text(text, reply_markup=builder.as_markup(), parse_mode='HTML')
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode='HTML')
# ------------------------------
# Команда /help
# ------------------------------
@router.message(Command("help"))
async def help_cmd(message: Message, state: FSMContext):
    await show_help(message, state)


class AdminStates(StatesGroup):
    ADD_TIME = State()
    REMOVE_TIME = State()
    CREATE_STATIC_PROFILE = State()
    SEND_MESSAGE = State()
    ADD_TIME_USER = State()
    REMOVE_TIME_USER = State()
    ADD_TIME_AMOUNT = State()
    REMOVE_TIME_AMOUNT = State()
    SEND_MESSAGE_TARGET = State()

def split_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list:
    """Разбивает текст на части указанной максимальной длины"""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        part = text[:max_length]
        last_newline = part.rfind('\n')
        if last_newline != -1:
            part = part[:last_newline]
        parts.append(part)
        text = text[len(part):].lstrip()
    return parts

async def show_menu(bot: Bot, chat_id: int, message_id: int = None):
    """Функция для отображения меню (может как редактировать существующее сообщение, так и отправлять новое)"""
    user = await get_user(chat_id)
    if not user:
        return
    
    status, expire_date = check_subscription_status(user)
    
    text = (
        f"**Имя профиля**: `{user.full_name}`\n"
        f"**Id**: `{user.telegram_id}`\n"
        f"**Подписка**: `{status}`\n"
        f"**Дата окончания подписки**: `{expire_date}`"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💵 Продлить" if status=="Активна" else "💵 Оплатить", callback_data="renew_sub")
    builder.button(text="✅ Подключить", callback_data="connect")
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.button(text="ℹ️ Помощь", callback_data="help")
    
    if user.is_admin:
        builder.button(text="⚠️ Админ. меню", callback_data="admin_menu")
    
    builder.adjust(2, 2, 1)
    
    if message_id:
        # Редактируем существующее сообщение
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    else:
        # Отправляем новое сообщение
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )

@router.message(Command("start"))
async def start_cmd(message: Message, bot: Bot):
    logger.info(f"ℹ️  Start command from {message.from_user.id}")
    user = await get_user(message.from_user.id)
    
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    
    # Обновляем данные пользователя если они изменились
    update_data = {}
    if user:
        if user.full_name != message.from_user.full_name:
            update_data["full_name"] = message.from_user.full_name
        if user.username != message.from_user.username:
            update_data["username"] = message.from_user.username
    else:
        is_admin = message.from_user.id in config.ADMINS
        user = await create_user(
            telegram_id=message.from_user.id, 
            full_name=message.from_user.full_name,
            username=message.from_user.username,
            is_admin=is_admin
        )
        await message.answer(
    f"👋 **Добро пожаловать в {bot_info.full_name}!**\n\n"
    "🚀 Здесь ты можете получить **стабильный и быстрый VPN**.\n\n"
    "🎁 **Бонус для новых пользователей:**\n"
    "— бесплатный тестовый период на **3 дня**\n\n"
    "👇 Нажмите на кнопку **ПОДКЛЮЧИТЬ**.",
    parse_mode="Markdown"
)
        await asyncio.sleep(2)
    
    # Обновляем данные если есть изменения
    if update_data:
        with Session() as session:
            db_user = session.query(User).get(user.id)
            for key, value in update_data.items():
                setattr(db_user, key, value)
            session.commit()
            logger.info(f"🔄 Updated user data: {message.from_user.id}")
    
    await show_menu(bot, message.from_user.id)

@router.message(Command("menu"))
async def menu_cmd(message: Message, bot: Bot):
    user = await get_user(message.from_user.id)
    if not user:
        await start_cmd(message, bot)
        return
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    
    # Проверяем изменения данных
    update_data = {}
    if user.full_name != message.from_user.full_name:
        update_data["full_name"] = message.from_user.full_name
    if user.username != message.from_user.username:
        update_data["username"] = message.from_user.username
    
    # Обновляем данные если есть изменения
    if update_data:
        with Session() as session:
            db_user = session.query(User).get(user.id)
            for key, value in update_data.items():
                setattr(db_user, key, value)
            session.commit()
            logger.info(f"🔄 Updated user data in menu: {message.from_user.id}")
    
    await show_menu(bot, message.from_user.id)


@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_help(callback.message, state)

async def show_help(message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🌐 Проверить IP", 
        url="https://2ip.ru/"
    )
    builder.button(text="🚀 Speedtest",callback_data="admin_speedtest")# speedtest
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    builder.adjust(2, 1)

    text = (
    "*🆘 Помощь*\n\n"
    "💬 Отправь в ответ текстовое сообщение или изображение \\(скриншот\\), "
    "чтобы мы получили твоё обращение\\.\n\n"
    "🌐 Проверить работу VPN можно на сайте *2ip\\.ru*\n"
    "📍 Ваш IP адрес: *185\\.82\\.218\\.35*\n\n"
    "> Для подключения VPN жми команду:✅  */connect*\n"
    "> Там ты найдёшь доступные приложения и свой токен\\.\n"
    )

    await state.set_state(HelpState.waiting_for_message)

    await message.answer(
        text,
        parse_mode="Markdownv2",
        reply_markup=builder.as_markup()
    )

@router.message(HelpState.waiting_for_message, F.photo)
async def help_forward_photo(message: Message, state: FSMContext):
    user = message.from_user

    caption = (
        "🆘 <b>Новое обращение (изображение)</b>\n\n"
        f"👤 Пользователь: {user.full_name}\n"
        f"🔗 Username: @{user.username if user.username else 'нет'}\n"
        f"🆔 ID: {user.id}"
    )

    photo = message.photo[-1].file_id  # самое большое фото

    for admin_id in config.ADMINS:
        await message.bot.send_photo(
            admin_id,
            photo=photo,
            caption=caption,
            parse_mode="HTML"
        )

        # если пользователь добавил подпись к фото
        if message.caption:
            await message.bot.send_message(
                admin_id,
                f"💬 <b>Комментарий пользователя:</b>\n{message.caption}",
                parse_mode="HTML"
            )

    await message.answer(
        "✅ <b>Обращение с изображением отправлено</b>\n\n"
        "Администратор свяжется с тобой в течение <b>3 часов</b>.",
        parse_mode="HTML"
    )

    await state.clear()

@router.message(HelpState.waiting_for_message)
async def help_forward(message: Message, state: FSMContext):
    user = message.from_user

    admin_text = (
        "🆘 <b>Новое обращение</b>\n\n"
        f"👤 Пользователь: {user.full_name}\n"
        f"🔗 Username: @{user.username if user.username else 'нет'}\n"
        f"🆔 ID: {user.id}\n\n"
        f"💬 Сообщение:\n{message.text}"
    )

    for admin_id in config.ADMINS:
        await message.bot.send_message(
            admin_id,
            admin_text,
            parse_mode="HTML"
        )

    await message.answer(
        "✅ <b>Обращение отправлено</b>\n\n"
        "Администратор свяжется с тобой в течение <b>3 часов</b>.\n"
        "Пожалуйста, не дублируй запрос — это ускорит обработку 🙏",
        parse_mode="HTML"
    )

    await state.clear()
    


@router.message(HelpState.waiting_for_message)
async def help_unsupported(message: Message):
    await message.answer(
        "❗️Пожалуйста, отправь текст или изображение.\n"
        "Другие типы сообщений пока не поддерживаются."
    )



@router.callback_query(F.data == "renew_sub")
async def renew_subscription(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()

    for months in sorted(config.PRICES.keys()):
        rub_price = config.calculate_price(months)
        stars_price = config.STARS_PRICES.get(months)

        price_info = config.PRICES[months]
        discount_text = (
            f" (-{price_info['discount_percent']}%)"
            if price_info["discount_percent"] > 0
            else ""
        )

        button_text = (
            f"{months} мес. — "
            f"{rub_price} ₽{discount_text} / "
            f"{stars_price} ⭐"
        )

        builder.button(
            text=button_text,
            callback_data=f"choose_pay_{months}"
        )

    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "💵 **Выберите период подписки:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )



@router.callback_query(F.data.startswith("choose_pay_"))
async def choose_payment_method(callback: CallbackQuery):
    await callback.answer()

    months = int(callback.data.split("_")[2])

    builder = InlineKeyboardBuilder()
    builder.button(
        text="⭐ Telegram Srars",
        callback_data=f"pay_stars_{months}"
    )
    builder.button(
        text="💳 Перевод (T-Bank)",
        callback_data=f"pay_tinkoff_{months}"
    )
    builder.button(text="⬅️ Назад", callback_data="renew_sub")
    builder.adjust(1)

    await callback.message.edit_text(
        "💳 **Выберите способ оплаты:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    
@router.callback_query(F.data.startswith("pay_stars_"))
async def pay_stars(callback: CallbackQuery):
    await callback.answer()

    months = int(callback.data.split("_")[2])
    stars_price = config.STARS_PRICES[months]

    prices = [
        LabeledPrice(
            label=f"Подписка на {months} мес.",
            amount=stars_price
        )
    ]

    await callback.message.answer_invoice(
        title="Подписка",
        description=f"Доступ на {months} мес.",
        prices=prices,
        currency="XTR",
        payload=f"subscription_{months}"
    )




@router.callback_query(F.data.startswith("pay_tinkoff_"))
async def process_tinkoff_payment(callback: CallbackQuery):
    await callback.answer()

    months = int(callback.data.split("_")[2])
    final_price = config.calculate_price(months)
    #ЛОГИРУЕМ НАЖАТИЕ «ОПЛАТИТЬ»
    payment_logger.info(
        f"PAY_INIT | user_id={callback.from_user.id} | months={months} | price={final_price}"
    )

    user_id = callback.from_user.id
    suffix = "месяц" if months == 1 else "месяца" if months in (2, 3, 4) else "месяцев"

    text = (
        "💳 **Оплата подписки VPN**\n\n"
        f"📦 Период: **{months} {suffix}**\n"
        f"💰 Сумма: **{final_price} ₽**\n\n"
        "⚠️ **ВАЖНО!**\n"
        "В комментарии к переводу укажите ваш **Telegram ID/USER**:\n"
        f"`{user_id}`\n\n"
        "После оплаты нажмите кнопку **«Я оплатил»**"
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="💸 Перейти к оплате",
        url=config.TINKOFF_PAY_URL
    )
    builder.button(
        text="✅ Я оплатил",
        callback_data=f"paid_{months}"
    )
    builder.button(
        text="⬅️ Назад",
        callback_data="back_to_menu"
    )
    builder.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ОБНОВЛЕННЫЙ обработчик подтверждения оплаты
@router.callback_query(F.data.startswith("paid_"))
async def confirm_payment(callback: CallbackQuery, bot: Bot):
    await callback.answer()

    months = int(callback.data.split("_")[1])
    user = await get_user(callback.from_user.id)

    suffix = "месяц" if months == 1 else "месяца" if months in (2, 3, 4) else "месяцев"

    await callback.message.edit_text(
        "⏳ **Платёж отправлен на проверку**\n\n"
        "Обычно проверка занимает до **10 минут**.\n"
        "После подтверждения подписка будет активирована.\n\n"
        "🔔 Вы получите уведомление, когда администратор подтвердит оплату.",
        parse_mode="Markdown"
    )

    admin_text = (
    "💰 *НОВАЯ ОПЛАТА*\n\n"
    f"👤 *Пользователь:* {user.full_name}\n"
    f"🆔 *Telegram ID:* `{user.telegram_id}`\n"
    f"📅 *Период:* {months} {suffix}\n"
    f"🕐 *Время:* {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n"
    "⚠️ *Требуется подтверждение администратора*"
)

    for admin_id in config.ADMINS:
        try:
            # Добавляем кнопку для быстрого подтверждения
            builder = InlineKeyboardBuilder()
            builder.button(
                text="✅ Подтвердить оплату", 
                callback_data=f"confirm_payment_{user.telegram_id}_{months}"
            )
            
            await bot.send_message(
                admin_id, 
                admin_text, 
                parse_mode="Markdown",
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")

@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@router.message(F.successful_payment)
async def process_successful_payment(message: Message, bot: Bot):
    try:
        # Извлекаем информацию из payload
        payload = message.successful_payment.invoice_payload
        if payload.startswith("subscription_"):
            months = int(payload.split("_")[1])
            final_price = config.calculate_price(months)  # Переводим обратно в рубли
            stars_paid = message.successful_payment.total_amount
            
            # Получаем информацию о пользователе
            user = await get_user(message.from_user.id)
            if not user:
                await message.answer("❌ Ошибка: пользователь не найден")
                return
            
            # Определяем тип действия (покупка или продление)
            now = datetime.utcnow()
            action_type = "продлена" if user.subscription_end > now else "куплена"
            
            # Обновляем подписку с использованием новой функции
            new_end_date = await update_subscription(message.from_user.id, months, is_admin_action=False)
            suffix = "месяц" if months == 1 else "месяца" if months in (2,3,4) else "месяцев"
            
            if new_end_date:
                # Отправляем уведомление пользователю
                await send_subscription_extended_notification(
                    bot=bot,
                    telegram_id=message.from_user.id,
                    months=months,
                    new_end_date=new_end_date,
                    is_admin_action=False
                )
                
                # Создаем клавиатуру с кнопкой подключения
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Подключить VPN", callback_data="connect")]
                ])
                
                # Отправляем сообщение с кнопкой
                await message.answer(
                    f"✅ Оплата прошла успешно!\n"
                    f"Ваша подписка {action_type} на {months} {suffix}.\n\n"
                    f"Спасибо за покупку! 🎉\n"
                    f"Для подключения нажмите кнопку ниже:",
                    reply_markup=keyboard
                )
                
                # Отправляем уведомление администраторам
                admin_message = (
                    f"{action_type.capitalize()} подписка пользователем "
                    f"`{user.full_name}` | `{user.telegram_id}` "
                    f"на {months} {suffix} - {final_price}₽"
                )
                
                for admin_id in config.ADMINS:
                    try:
                        await bot.send_message(admin_id, admin_message, parse_mode='Markdown')
                    except Exception as e:
                        logger.error(f"🛑 Failed to send notification to admin {admin_id}: {e}")
            else:
                await message.answer("❌ Ошибка при обновлении подписки")
    except Exception as e:
        logger.error(f"🛑 Successful payment processing error: {e}")
        await message.answer("❌ Ошибка при обработке платежа")
        
        
#speedtest  
@router.callback_query(F.data == "admin_speedtest")
async def admin_speedtest(callback: CallbackQuery):
    await callback.answer("🚀 Запускаю speedtest на XRay сервере...")

    import aiohttp
    import os
    from dotenv import load_dotenv

    load_dotenv()
    XRAY_SPEEDTEST_URL = os.getenv("XRAY_SPEEDTEST_URL")
    XRAY_TOKEN = os.getenv("XRAY_TOKEN")

    if not XRAY_SPEEDTEST_URL or not XRAY_TOKEN:
        await callback.message.answer("❌ Speedtest не настроен (.env)")
        return

    timeout = aiohttp.ClientTimeout(total=75)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                XRAY_SPEEDTEST_URL,
                headers={"X-Token": XRAY_TOKEN}
            ) as resp:

                if resp.status != 200:
                    text = await resp.text()
                    await callback.message.answer(
                        f"❌ Ошибка агента XRay\n"
                        f"HTTP `{resp.status}`\n"
                        f"`{text}`"
                    )
                    return

                data = await resp.json()

    except aiohttp.ClientError as e:
        await callback.message.answer(f"❌ Ошибка соединения:\n`{e}`")
        return

    except Exception as e:
        await callback.message.answer(f"❌ Неизвестная ошибка:\n`{e}`")
        return

    # 🔹 безопасно достаём поля
    server_name = data.get("server_name", "Unknown")
    server_country = data.get("server_country", "Unknown")
    server_sponsor = data.get("server_sponsor", "Unknown")
    client_ip = data.get("client_ip", "Unknown")
    download = data.get("download_mbps", 0)
    upload = data.get("upload_mbps", 0)
    ping = data.get("ping_ms", 0)
    packet_loss = data.get("packet_loss", 0)

    # 🔹 Формируем сообщение для Telegram
    msg = (
        "🚀 **SpeedTest с сервера XRay**\n\n"
        f"📍 Сервер: `{server_name}` ({server_country})\n"
        f"📌 Провайдер: `{server_sponsor}`\n"
        f"🌐 IP клиента: `{client_ip}`\n\n"
        f"⬇️ **Download**: `{download} Mbps`\n"
        f"⬆️ **Upload**: `{upload} Mbps`\n"
        f"⏱ **Ping**: `{ping} ms`\n"
        f"📶 **Packet loss**: `{packet_loss}%`"
    )

    await callback.message.answer(msg, parse_mode="Markdown")
    


# ОБНОВЛЕННОЕ админ-меню с кнопкой тестирования уведомлений
@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user or not user.is_admin:
        await callback.answer("🛑 Доступ запрещен!")
        return
    
    stats = await db_user_stats()
    total = stats["total"]
    with_sub = stats["with_active_subscription"]
    without_sub = stats["without_subscription"]
    online_count = await get_online_users()
    
    text = (
        "**Административное меню**\n\n"
        f"**Всего пользователей**: `{total}`\n"
        f"**С подпиской/Без подписки**: `{with_sub}`/`{without_sub}`\n"
        f"**Онлайн**: `{online_count}` | **Офлайн**: `{with_sub - online_count}`"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="+ время", callback_data="admin_add_time")
    builder.button(text="- время", callback_data="admin_remove_time")
    builder.button(text="📋 Подписки", callback_data="admin_user_list")
    builder.button(text="📊 Статистика", callback_data="admin_network_stats")
    builder.button(text="📢 Рассылка", callback_data="admin_send_message")
    builder.button(text="🔔 Тест СМС", callback_data="admin_test_notification")  # Новая кнопка
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    
    builder.adjust(2, 2, 2, 1, 1, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode='Markdown')



# НОВЫЙ обработчик тестирования уведомлений
@router.callback_query(F.data == "admin_test_notification")
async def admin_test_notification(callback: CallbackQuery, bot: Bot):
    """Тестирование системы уведомлений"""
    try:
        await callback.answer()
        
        # Отправляем тестовое уведомление себе
        success = await send_test_notification(bot, callback.from_user.id)
        
        if success:
            await callback.message.answer(
                "✅ *Тестовое уведомление отправлено!*\n\n"
                "Проверьте, получили ли вы сообщение.",
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer(
                "❌ *Ошибка отправки уведомления*\n\n"
                "Проверьте логи для деталей.",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"❌ Test notification error: {e}")
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

# Обработчики для управления временем подписки (ОБНОВЛЕННЫЕ)
@router.callback_query(F.data == "admin_add_time")
async def admin_add_time_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # Снимаем анимацию
    await callback.message.answer("Введите Telegram ID пользователя:")
    await state.set_state(AdminStates.ADD_TIME_USER)

@router.message(AdminStates.ADD_TIME_USER)
async def admin_add_time_user(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await message.answer("Введите количество времени в формате:\nМесяцы Дни Часы Минуты\nПример: 1 0 0 0")
        await state.set_state(AdminStates.ADD_TIME_AMOUNT)
    except ValueError:
        await message.answer("Ошибка: ID должен быть числом")

# ОБНОВЛЕННЫЙ обработчик добавления времени
@router.message(AdminStates.ADD_TIME_AMOUNT)
async def admin_add_time_amount(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = data['user_id']
    parts = message.text.split()
    
    if len(parts) != 4:
        await message.answer("Ошибка: нужно ввести 4 числа")
        return
    
    try:
        months, days, hours, minutes = map(int, parts)
        
        # Используем новую функцию для добавления времени
        new_end_date = await add_time_to_subscription(
            telegram_id=user_id,
            months=months,
            days=days,
            hours=hours,
            minutes=minutes
        )
        
        if new_end_date:
            # Отправляем уведомление пользователю
            total_months = round((months * 30 + days) / 30, 1)
            await send_subscription_extended_notification(
                bot=bot,
                telegram_id=user_id,
                months=total_months,
                new_end_date=new_end_date,
                is_admin_action=True
            )
            
            # Формируем строку с добавленным временем
            time_str_parts = []
            if months > 0:
                time_str_parts.append(f"{months} мес.")
            if days > 0:
                time_str_parts.append(f"{days} дн.")
            if hours > 0:
                time_str_parts.append(f"{hours} час.")
            if minutes > 0:
                time_str_parts.append(f"{minutes} мин.")
            
            time_str = ", ".join(time_str_parts)
            
            await message.answer(
                f"✅ Время добавлено пользователю {user_id}:\n"
                f"📅 Добавлено: {time_str}\n"
                f"📅 Новая дата окончания: {new_end_date.strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        logger.error(f"❌ Error adding time: {e}")
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_remove_time")
async def admin_remove_time_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # Снимаем анимацию
    await callback.message.answer("Введите Telegram ID пользователя:")
    await state.set_state(AdminStates.REMOVE_TIME_USER)

@router.message(AdminStates.REMOVE_TIME_USER)
async def admin_remove_time_user(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await message.answer("Введите количество времени в формате:\nМесяцы Дни Часы Минуты\nПример: 1 0 0 0")
        await state.set_state(AdminStates.REMOVE_TIME_AMOUNT)
    except ValueError:
        await message.answer("Ошибка: ID должен быть числом")

# ОБНОВЛЕННЫЙ обработчик удаления времени
@router.message(AdminStates.REMOVE_TIME_AMOUNT)
async def admin_remove_time_amount(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = data['user_id']
    parts = message.text.split()
    
    if len(parts) != 4:
        await message.answer("Ошибка: нужно ввести 4 числа")
        return
    
    try:
        months, days, hours, minutes = map(int, parts)
        
        # Используем новую функцию для удаления времени
        new_end_date = await remove_time_from_subscription(
            telegram_id=user_id,
            months=months,
            days=days,
            hours=hours,
            minutes=minutes
        )
        
        if new_end_date:
            # Формируем строку с удаленным временем
            time_str_parts = []
            if months > 0:
                time_str_parts.append(f"{months} мес.")
            if days > 0:
                time_str_parts.append(f"{days} дн.")
            if hours > 0:
                time_str_parts.append(f"{hours} час.")
            if minutes > 0:
                time_str_parts.append(f"{minutes} мин.")
            
            time_str = ", ".join(time_str_parts)
            
            await message.answer(
                f"✅ Время удалено у пользователя {user_id}:\n"
                f"📅 Удалено: {time_str}\n"
                f"📅 Новая дата окончания: {new_end_date.strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        logger.error(f"❌ Error removing time: {e}")
    finally:
        await state.clear()

# Обработчики для вывода списка пользователей
@router.callback_query(F.data == "admin_user_list")
async def admin_user_list(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ С подпиской", callback_data="user_list_active")
    builder.button(text="🛑 Без подписки", callback_data="user_list_inactive")
    builder.button(text="⏱️ Статические профили", callback_data="static_profiles_menu")
    builder.button(text="⬅️ Назад", callback_data="admin_menu")
    builder.adjust(1, 1, 1)
    await callback.message.edit_text("**Выберите фильтр**", reply_markup=builder.as_markup(), parse_mode='Markdown')

@router.callback_query(F.data == "user_list_active")
async def handle_user_list_active(callback: CallbackQuery):
    users = await get_all_users(with_active_subscription=True)
    await callback.answer()
    if not users:
        await callback.answer("Нет пользователей с активной подпиской")
        return
    
    text = "👤 <b>Пользователи с активной подпиской:</b>\n\n"
    for user in users:
        expire_date = user.subscription_end.strftime("%d.%m.%Y %H:%M")
        username = f"@{user.username}" if user.username else "none"
        user_line = f"• {user.full_name} ({username} | <code>{user.telegram_id}</code>) - до <code>{expire_date}</code>\n"
        
        # Если текст становится слишком длинным, отправляем текущую часть и начинаем новую
        if len(text) + len(user_line) > MAX_MESSAGE_LENGTH:
            await callback.message.answer(text, parse_mode="HTML")
            text = "👤 <b>Пользователи с активной подпиской (продолжение):</b>\n\n"
        
        text += user_line
    
    # Отправляем оставшуюся часть текста
    await callback.message.answer(text, parse_mode="HTML")

@router.callback_query(F.data == "user_list_inactive")
async def handle_user_list_inactive(callback: CallbackQuery):
    await callback.answer()
    users = await get_all_users(with_active_subscription=False)
    if not users:
        await callback.answer("Нет пользователей без подписки")
        return
    
    text = "👤 <b>Пользователи без подписки:</b>\n\n"
    for user in users:
        username = f"@{user.username}" if user.username else "none"
        user_line = f"• {user.full_name} ({username} | <code>{user.telegram_id}</code>)\n"
        
        # Если текст становится слишком длинным, отправляем текущую часть и начинаем новую
        if len(text) + len(user_line) > MAX_MESSAGE_LENGTH:
            await callback.message.answer(text, parse_mode="HTML")
            text = "👤 <b>Пользователи без подписки (продолжение):</b>\n\n"
        
        text += user_line
    
    # Отправляем оставшуюся часть текста
    await callback.message.answer(text, parse_mode="HTML")

# Обработчики для рассылки сообщений
@router.callback_query(F.data == "admin_send_message")
async def admin_send_message_start(callback: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ С подпиской", callback_data="target_active")
    builder.button(text="🛑 Без подписки", callback_data="target_inactive")
    builder.button(text="👥 Всем пользователям", callback_data="target_all")
    builder.button(text="↩️ Назад", callback_data="admin_menu")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "Выберите целевую аудиторию для рассылки:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("target_"))
async def admin_send_message_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # Снимаем анимацию
    target = callback.data.split("_")[1]
    await state.update_data(target=target)
    await callback.message.answer("Введите сообщение для рассылки:")
    await state.set_state(AdminStates.SEND_MESSAGE)

@router.message(AdminStates.SEND_MESSAGE)
async def admin_send_message(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = data['target']
    text = message.text
    
    users = []
    if target == "active":
        users = await get_all_users(with_active_subscription=True)
    elif target == "inactive":
        users = await get_all_users(with_active_subscription=False)
    else:  # all
        users = await get_all_users()
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await bot.send_message(user.telegram_id, text)
            success += 1
        except Exception as e:
            logger.error(f"🛑 Ошибка отправки сообщения {user.telegram_id}: {e}")
            failed += 1
    
    await message.answer(
        f"📨 Результаты рассылки:\n\n"
        f"• Успешно: {success}\n"
        f"• Не удалось: {failed}\n"
        f"• Всего: {len(users)}"
    )
    await state.clear()

# НОВЫЙ обработчик для ручного подтверждения оплаты через кнопку
@router.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment_by_admin(callback: CallbackQuery, bot: Bot):
    """Подтверждение оплаты администратором через кнопку"""
    try:
        # Ожидаемый формат:
        # confirm_payment_{user_id}_{months}
        data = callback.data.split("_")

        if len(data) != 4:
            await callback.answer("❌ Некорректный запрос")
            return

        _, _, user_id, months = data

        user_id = int(user_id)
        months = int(months)

        # Обновляем подписку
        new_end_date = await update_subscription(
            user_id,
            months,
            True
        )

        if new_end_date:
            # Уведомляем пользователя
            await send_subscription_extended_notification(
                bot=bot,
                telegram_id=user_id,
                months=months,
                new_end_date=new_end_date,
                is_admin_action=True
            )

            # Ответ администратору
            await callback.answer("✅ Подписка успешно продлена!")

            suffix = (
                "месяц" if months == 1
                else "месяца" if months in (2, 3, 4)
                else "месяцев"
            )

            await callback.message.edit_text(
                f"✅ *Оплата подтверждена!*\n\n"
                f"👤 Пользователь: `{user_id}`\n"
                f"📅 Продлено на: {months} {suffix}\n"
                f"📅 Новая дата окончания: `{new_end_date.strftime('%d.%m.%Y %H:%M')}`\n\n"
                f"✅ Уведомление отправлено пользователю.",
                parse_mode="Markdown",
                reply_markup=None
            )
            await callback.answer("✅ Уже подтверждено", show_alert=False)


            

        else:
            await callback.answer("❌ Ошибка при продлении подписки")
            await callback.message.edit_text("❌ Произошла ошибка при продлении подписки")

    except Exception as e:
        logger.error(f"❌ Error confirming payment: {e}")
        await callback.answer("❌ Произошла ошибка")


# НОВАЯ команда для ручного подтверждения оплаты
@router.message(Command("confirm_payment"))
async def confirm_payment_command(message: Message, bot: Bot):
    """Команда для ручного подтверждения оплаты администратором"""
    user = await get_user(message.from_user.id)
    if not user or not user.is_admin:
        await message.answer("🛑 Доступ запрещен!")
        return
    
    try:
        # Парсим аргументы: /confirm_payment <user_id> <months>
        args = message.text.split()
        if len(args) < 3:
            await message.answer(
                "Использование:\n"
                "`/confirm_payment <user_id> <months>`\n\n"
                "Пример:\n"
                "`/confirm_payment 123456789 3`"
            )
            return
        
        user_id = int(args[1])
        months = int(args[2])
        
        # Обновляем подписку
        new_end_date = await update_subscription(user_id, months, is_admin_action=True)
        
        if new_end_date:
            # Отправляем уведомление пользователю
            await send_subscription_extended_notification(
                bot=bot,
                telegram_id=user_id,
                months=months,
                new_end_date=new_end_date,
                is_admin_action=True
            )
            
            suffix = "месяц" if months == 1 else "месяца" if months in (2, 3, 4) else "месяцев"
            
            await message.answer(
                f"✅ *Оплата подтверждена!*\n\n"
                f"👤 Пользователь: `{user_id}`\n"
                f"📅 Продлено на: {months} {suffix}\n"
                f"📅 Новая дата окончания: `{new_end_date.strftime('%d.%m.%Y %H:%M')}`\n\n"
                f"✅ Уведомление отправлено пользователю.",
                parse_mode="Markdown"
            )
        else:
            await message.answer(f"❌ Не удалось продлить подписку пользователю {user_id}")
            
    except ValueError:
        await message.answer("❌ Ошибка: user_id и months должны быть числами")
    except Exception as e:
        logger.error(f"❌ Confirm payment error: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

# Остальные обработчики остаются без изменений
@router.callback_query(F.data == "static_profiles_menu")
async def static_profiles_menu(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Добавить статический профиль", callback_data="static_profile_add")
    builder.button(text="📋 Вывести статические профили", callback_data="static_profile_list")
    builder.button(text="⬅️ Назад", callback_data="admin_user_list")
    builder.adjust(1)
    await callback.message.edit_text("**Выберите действие**", reply_markup=builder.as_markup(), parse_mode='Markdown')

@router.callback_query(F.data == "static_profile_add")
async def static_profile_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # Снимаем анимацию
    await callback.message.answer("Введите имя для статического профиля:")
    await state.set_state(AdminStates.CREATE_STATIC_PROFILE)

@router.message(AdminStates.CREATE_STATIC_PROFILE)
async def process_static_profile_name(message: Message, state: FSMContext):
    profile_name = message.text
    profile_data = await create_static_client(profile_name)
    
    if profile_data:
        vless_url = generate_vless_url(profile_data)
        await create_static_profile(profile_name, vless_url)
        profiles = await get_static_profiles()
        for profile in profiles:
            if profile.name == profile_name:
                id = profile.id
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑️ Удалить", callback_data=f"delete_static_{id}")
        await message.answer(f"Профиль создан!\n\n`{vless_url}`", reply_markup=builder.as_markup(), parse_mode='Markdown')
    else:
        await message.answer("Ошибка при создании профиля")
    
    await state.clear()

@router.callback_query(F.data == "static_profile_list")
async def static_profile_list(callback: CallbackQuery):
    profiles = await get_static_profiles()
    if not profiles:
        await callback.answer("Нет статических профилей")
        return
    
    for profile in profiles:
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑️ Удалить", callback_data=f"delete_static_{profile.id}")
        await callback.message.answer(
            f"**{profile.name}**\n`{profile.vless_url}`", 
            reply_markup=builder.as_markup(), parse_mode='Markdown'
        )

@router.callback_query(F.data.startswith("delete_static_"))
async def handle_delete_static_profile(callback: CallbackQuery):
    try:
        profile_id = int(callback.data.split("_")[-1])
        
        with Session() as session:
            profile = session.query(StaticProfile).filter_by(id=profile_id).first()
            if not profile:
                await callback.answer("⚠️ Профиль не найден")
                return
            
            success = await delete_client_by_email(profile.name)
            if not success:
                logger.error(f"🛑 Ошибка удаления клиента из инбаунда: {profile.name}")
            
            session.delete(profile)
            session.commit()
        
        await callback.answer("✅ Профиль удален!")
        await callback.message.delete()
    except Exception as e:
        logger.error(f"🛑 Ошибка при удалении статического профиля: {e}")
        await callback.answer("⚠️ Ошибка при удалении профиля")

@router.callback_query(F.data == "connect")
async def connect_profile(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("🛑 Ошибка профиля")
        return
    
    # 1. ПРОВЕРЯЕМ СТАТУС ПОДПИСКИ С ИСПОЛЬЗОВАНИЕМ MSK
    from datetime import datetime
    import pytz
    
    MSK = pytz.timezone("Europe/Moscow")
    
    # Если нет даты окончания подписки - подписка истекла
    if not user.subscription_end:
        await callback.answer("⚠️ У вас нет активной подписки!")
        await callback.message.edit_text(
            "❌ <b>Подписка не активна</b>\n\n"
            "У вас нет активной подписки.\n"
            "Для подключения VPN необходимо приобрести подписку.",
            parse_mode="HTML"
        )
        return
    
    # Текущее время в MSK
    now_msk = datetime.now(MSK)
    
    # Приводим subscription_end к MSK если нужно
    if user.subscription_end.tzinfo is None:
        subscription_end_msk = MSK.localize(user.subscription_end)
    else:
        subscription_end_msk = user.subscription_end.astimezone(MSK)
    
    # Проверяем истекла ли подписка
    if subscription_end_msk <= now_msk:
        await callback.answer("⚠️ Подписка истекла! Продлите подписку.")
        
        # Если есть профиль в XUI - удаляем его
        if user.vless_profile_data:
            try:
                profile_data = safe_json_loads(user.vless_profile_data, default={})
                email = profile_data.get("email")
                if email and email != "N/A":
                    await delete_client_by_email(email)
                    logger.info(f"🧹 Удален профиль истекшей подписки: {email}")
            except Exception as e:
                logger.error(f"Ошибка при удалении профиля: {e}")
        
        # Обновляем меню с информацией об истекшей подписке
        builder = InlineKeyboardBuilder()
        builder.button(text="💵 Продлить подписку", callback_data="renew_sub")
        builder.button(text="⬅️ Назад в меню", callback_data="back_to_menu")
        builder.adjust(1)
        
        expire_date = subscription_end_msk.strftime("%d-%m-%Y %H:%M")
        await callback.message.edit_text(
            f"❌ <b>Подписка истекла!</b>\n\n"
            f"Дата окончания: {expire_date}\n"
            f"Для восстановления доступа к VPN продлите подписку.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return
    
    # 2. ПОДПИСКА АКТИВНА - ПРОДОЛЖАЕМ
    if not user.vless_profile_data:
        # Создаем новый профиль
        await callback.message.edit_text("⚙️ Создаем ваш VPN профиль...")
        profile_data = await create_vless_profile(user.telegram_id)

        if not profile_data:
            await callback.message.edit_text(
                "🛑 Ошибка при создании профиля. Попробуйте позже."
            )
            return

        # Сохраняем профиль в БД
        with Session() as session:
            db_user = session.query(User).filter_by(
                telegram_id=user.telegram_id
            ).first()
            if db_user:
                db_user.vless_profile_data = json.dumps(profile_data)
                session.commit()
                logger.info(f"✅ Создан профиль для {user.telegram_id}: {profile_data['email']}")

        # 🔔 Уведомление админов
        for admin_id in config.ADMINS:
            try:
                await callback.bot.send_message(
                    admin_id,
                    "🟢 *Создан новый VPN-клиент*\n\n"
                    f"👤 Telegram ID: `{user.telegram_id}`\n"
                    f"👤 Telegram User: `{user.full_name}`\n"
                    f"📧 Email: `{profile_data['email']}`\n"
                    f"🌐 Inbound: `{profile_data['remark']}`\n"
                    f"🔐 Security: `{profile_data['security']}`\n"
                    f"⏰ Подписка до: `{subscription_end_msk.strftime('%d.%m.%Y %H:%M')}`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"⚠️ Admin notify error ({admin_id}): {e}")

        # Перечитываем пользователя
        user = await get_user(user.telegram_id)

    # 3. ГЕНЕРИРУЕМ И ПОКАЗЫВАЕМ ССЫЛКУ
    profile_data = safe_json_loads(user.vless_profile_data, default={})
    if not profile_data:
        await callback.message.edit_text("⚠️ У вас пока нет созданного профиля.")
        return
        
    vless_url = generate_vless_url(profile_data)
    
    # Рассчитываем сколько осталось дней
    days_left = (subscription_end_msk - now_msk).days
    
    text = (
        f"🎉 <b>Ваш VPN профиль!</b>\n\n"
        f"📅 <b>Подписка активна</b> (осталось {days_left} дней)\n"
        f"⏰ Действует до: {subscription_end_msk.strftime('%d.%m.%Y %H:%M')}\n\n"
        "ℹ️ <b>Инструкция по подключению:</b>\n"
        "1. Скачайте приложение для вашей платформы\n"
        "2. Скопируйте эту ссылку и импортируйте в приложение:\n"
        f"<pre>{vless_url}</pre>\n\n"
        "3. Активируйте соединение в приложении."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text='🖥️ Windows [V2RayN]', url='https://github.com/2dust/v2rayN/releases/download/7.13.8/v2rayN-windows-64-desktop.zip')
    builder.button(text='🐧 Linux [NekoBox]', url='https://github.com/MatsuriDayo/nekoray/releases/download/4.0.1/nekoray-4.0.1-2024-12-12-debian-x64.deb')
    builder.button(text='🍎 Mac [V2RayU]', url='https://github.com/yanue/V2rayU/releases/download/v4.2.6/V2rayU-64.dmg')
    builder.button(text='🍏 iOS [V2RayTun]', url='https://apps.apple.com/ru/app/v2raytun/id6476628951')
    builder.button(text='🤖 Android [V2RayNG]', url='https://github.com/2dust/v2rayNG/releases/download/1.10.16/v2rayNG_1.10.16_arm64-v8a.apk')
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_menu")
    builder.adjust(2, 2, 1, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode='html')

@router.callback_query(F.data == "stats")
async def user_stats(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user or not user.vless_profile_data:
        await callback.answer("⚠️ Профиль не создан")
        return
    
    await callback.message.edit_text("⚙️ Загружаем вашу статистику...")
    
    # Статистика использования трафика
    profile_data = safe_json_loads(user.vless_profile_data, default={})
    stats = await get_user_stats(profile_data["email"])

    logger.debug(stats)
    
    # Обработка аплоада
    upload = f"{stats.get('upload', 0) / 1024 / 1024:.2f}"
    upload_size = 'MB' if int(float(upload)) < 1024 else 'GB'
    if upload_size == "GB":
        upload = f"{float(upload) / 1024:.2f}"

    # Обработка даунлоада
    download = f"{stats.get('download', 0) / 1024 / 1024:.2f}"
    download_size = 'MB' if int(float(download)) < 1024 else 'GB'
    if download_size == "GB":
        download = f"{float(download) / 1024:.2f}"
    
    # Статус подписки
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc)
    
    # Приводим subscription_end к aware datetime, если он naive
    if user.subscription_end:
        # Проверяем тип даты
        if user.subscription_end.tzinfo is None:
            # Если naive, добавляем UTC
            subscription_end = user.subscription_end.replace(tzinfo=timezone.utc)
        else:
            subscription_end = user.subscription_end
        
        if subscription_end > now:
            days_left = (subscription_end - now).days
            status_text = f"📅 Подписка активна\n⏳ Осталось дней: **{days_left}**"
        else:
            status_text = "⚠️ **Подписка истекла**"
    else:
        status_text = "⚠️ **Подписка не установлена**"
    
    await callback.message.delete()
    
    text = (
        "📊 **Ваша статистика:**\n\n"
        f"🔼 Загружено: `{upload} {upload_size}`\n"
        f"🔽 Скачано: `{download} {download_size}`\n\n"
        f"{status_text}"
    )
    
    await callback.message.answer(text, parse_mode='Markdown')

@router.callback_query(F.data == "admin_network_stats")
async def network_stats(callback: CallbackQuery):
    stats = await get_global_stats()

    upload = f"{stats.get('upload', 0) / 1024 / 1024:.2f}"
    upload_size = 'MB' if int(float(upload)) < 1024 else 'GB'
    if upload_size == "GB":
        upload = f"{int(float(upload) / 1024):.2f}"

    download = f"{stats.get('download', 0) / 1024 / 1024:.2f}"
    download_size = 'MB' if int(float(download)) < 1024 else 'GB'
    if download_size == "GB":
        download = f"{int(float(download) / 1024):.2f}"
    
    await callback.answer()
    text = (
        "📊 **Статистика использования сети:**\n\n"
        f"🔼 Upload - `{upload} {upload_size}` | 🔽 Download - `{download} {download_size}`"
    )
    await callback.message.edit_text(text, parse_mode='Markdown')

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    await show_menu(bot, callback.from_user.id, callback.message.message_id)

def setup_handlers(dp: Dispatcher):
    dp.include_router(router)
    logger.info("✅ Handlers setup completed")

def safe_json_loads(data, default=None):
    if not data:
        return default
    try:
        return json.loads(data)
    except Exception:
        return default