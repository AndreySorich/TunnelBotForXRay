# logging_config.py
import logging
import coloredlogs

def setup_logging():
    """Настройка логирования для всего проекта"""
    
    # Создаем форматтер
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Основной логгер
    main_logger = logging.getLogger()
    main_logger.setLevel(logging.INFO)
    
    # Очищаем старые обработчики
    main_logger.handlers.clear()
    
    # 1. Файловый обработчик для всех логов
    file_handler = logging.FileHandler('bot.log', encoding='utf-8', mode='a')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(log_format, date_format)
    file_handler.setFormatter(file_formatter)
    main_logger.addHandler(file_handler)
    
    # 2. Консольный обработчик с цветным выводом
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Устанавливаем coloredlogs для консоли
    coloredlogs.install(
        level='INFO',
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
        logger=main_logger
    )
    
    # 3. Отдельный логгер для платежей
    payments_logger = logging.getLogger('payments')
    payments_logger.setLevel(logging.INFO)
    
    payments_file_handler = logging.FileHandler('payments.log', encoding='utf-8', mode='a')
    payments_file_handler.setLevel(logging.INFO)
    payments_formatter = logging.Formatter(log_format, date_format)
    payments_file_handler.setFormatter(payments_formatter)
    
    payments_logger.addHandler(payments_file_handler)
    payments_logger.propagate = False  # Не дублируем логи в основной файл
    
    # 4. Отдельный логгер для ошибок
    error_logger = logging.getLogger('errors')
    error_logger.setLevel(logging.ERROR)
    
    error_file_handler = logging.FileHandler('errors.log', encoding='utf-8', mode='a')
    error_file_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(log_format, date_format)
    error_file_handler.setFormatter(error_formatter)
    
    error_logger.addHandler(error_file_handler)
    error_logger.propagate = False
    
    # Настройка для aiogram
    aiogram_logger = logging.getLogger('aiogram')
    aiogram_logger.setLevel(logging.INFO)
    
    # Отключаем слишком подробные логи aiogram
    logging.getLogger('aiogram.event').setLevel(logging.WARNING)
    
    return main_logger