import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Базовые настройки
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    OWNER_TELEGRAM_ID: int = int(os.getenv("OWNER_TELEGRAM_ID", 0))
    
    # Новые настройки для публичного режима
    PUBLIC_MODE: bool = os.getenv("PUBLIC_MODE", "true").lower() == "true"
    ALLOWED_USERS: List[int] = field(default_factory=list)
    BANNED_USERS: List[int] = field(default_factory=list)
    
    # Режим работы
    TELEGRAM_MODE: str = os.getenv("TELEGRAM_MODE", "public")
    
    # База данных
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/app.db")
    MEDIA_DIR: str = os.getenv("MEDIA_DIR", "data/media")
    
    # SAVE MODE
    SAVE_MODE_ENABLED: bool = os.getenv("SAVE_MODE_ENABLED", "true").lower() == "true"
    SAVE_MEDIA_ENABLED: bool = os.getenv("SAVE_MEDIA_ENABLED", "true").lower() == "true"
    MAX_MEDIA_SIZE_MB: int = int(os.getenv("MAX_MEDIA_SIZE_MB", 50))
    
    # Шифрование
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    
    # AI Настройки
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Другие настройки
    REPEAT_DELAY_MIN_SECONDS: int = int(os.getenv("REPEAT_DELAY_MIN_SECONDS", 1))
    REPEAT_DELAY_MAX_SECONDS: int = int(os.getenv("REPEAT_DELAY_MAX_SECONDS", 3))
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")
    
    def __post_init__(self):
        # Парсим списки пользователей из переменных окружения
        allowed = os.getenv("ALLOWED_USERS", "")
        if allowed and allowed != "*":
            self.ALLOWED_USERS = [int(x.strip()) for x in allowed.split(",") if x.strip()]
        
        banned = os.getenv("BANNED_USERS", "")
        if banned:
            self.BANNED_USERS = [int(x.strip()) for x in banned.split(",") if x.strip()]


settings = Settings()