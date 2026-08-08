import os
from typing import Optional, List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str
    BOT_USERNAME: str = "laosllebot"
    OWNER_TELEGRAM_ID: int

    # База данных
    DATABASE_URL: str = "sqlite+aiosqlite:///data/app.db"
    MEDIA_DIR: str = "data/media"

    # Режим работы
    TELEGRAM_MODE: str = "business"
    PUBLIC_MODE: bool = True
    ALLOWED_USERS: List[int] = []
    BANNED_USERS: List[int] = []

    # SAVE MODE
    SAVE_MODE_ENABLED: bool = True
    SAVE_MEDIA_ENABLED: bool = True
    MAX_MEDIA_SIZE_MB: int = 50

    # Шифрование
    ENCRYPTION_KEY: Optional[str] = None

    # AI
    LLM_PROVIDER: str = "anthropic"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # Реферальная система
    REFERRAL_BONUS_REFERRER_DAYS: int = 3
    REFERRAL_BONUS_REFERRED_DAYS: int = 1

    # Подписка
    SUBSCRIPTION_PRICE_STARS: int = 100
    SUBSCRIPTION_DAYS: int = 30
    TRIAL_DAYS: int = 1

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()