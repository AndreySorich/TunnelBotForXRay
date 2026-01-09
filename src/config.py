import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict
from typing import ClassVar, Dict

load_dotenv()
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

class Config(BaseModel):
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMINS: List[int] = Field(default_factory=list)

    XUI_API_URL: str = os.getenv("XUI_API_URL", "http://localhost:54321")
    XUI_BASE_PATH: str = os.getenv("XUI_BASE_PATH", "/panel")
    XUI_USERNAME: str = os.getenv("XUI_USERNAME", "admin")
    XUI_PASSWORD: str = os.getenv("XUI_PASSWORD", "admin")
    XUI_HOST: str = os.getenv("XUI_HOST", "your-server.com")
    XUI_SERVER_NAME: str = os.getenv("XUI_SERVER_NAME", "domain.com")

    PAYMENT_TOKEN: str = os.getenv("PAYMENT_TOKEN", "")
    INBOUND_ID: int = Field(default=os.getenv("INBOUND_ID", 1))

    REALITY_PUBLIC_KEY: str = os.getenv("REALITY_PUBLIC_KEY", "")
    REALITY_FINGERPRINT: str = os.getenv("REALITY_FINGERPRINT", "chrome")
    REALITY_SNI: str = os.getenv("REALITY_SNI", "example.com")
    REALITY_SHORT_ID: str = os.getenv("REALITY_SHORT_ID", "1234567890")
    REALITY_SPIDER_X: str = os.getenv("REALITY_SPIDER_X", "/")
    
    STARS_PRICES: ClassVar[Dict[int, int]] = {
    1: 150,
    3: 350,
    6: 600,
    12: 1300
}


    # 💳 Ссылка на Тинькофф
    _TINKOFF_PAY_URL: str = os.getenv(
        "TINKOFF_PAY_URL",
        "https://www.tinkoff.ru/rm/r_JhgtjeuVoI.bxWbcPNmwR/7Kw2n97416"
    )

    # Настройки цен и скидок
    PRICES: Dict[int, Dict[str, int]] = {
        1: {"base_price": 200, "discount_percent": 0},
        3: {"base_price": 600, "discount_percent": 0},
        6: {"base_price": 1000, "discount_percent": 20},
        12: {"base_price": 2200, "discount_percent": 30}
    }
    

    @property
    def TINKOFF_PAY_URL(self) -> str:
        if not self._TINKOFF_PAY_URL:
            raise ValueError("TINKOFF_PAY_URL is not configured")
        return self._TINKOFF_PAY_URL

    @field_validator('ADMINS', mode='before')
    def parse_admins(cls, value):
        if isinstance(value, str):
            return [int(admin) for admin in value.split(",") if admin.strip()]
        return value or []

    @field_validator('INBOUND_ID', mode='before')
    def parse_inbound_id(cls, value):
        if isinstance(value, str):
            return int(value)
        return value or 15

    def calculate_price(self, months: int) -> int:
        if months not in self.PRICES:
            return 0

        price_info = self.PRICES[months]
        base_price = price_info["base_price"]
        discount_percent = price_info["discount_percent"]

        discount_amount = (base_price * discount_percent) // 100
        return base_price - discount_amount


config = Config(
    ADMINS=os.getenv("ADMINS", ""),
    INBOUND_ID=os.getenv("INBOUND_ID", 15)
)
