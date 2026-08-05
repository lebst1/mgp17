import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    OWNER_TELEGRAM_ID: int = int(os.getenv("OWNER_TELEGRAM_ID", 0))
    
    PUBLIC_MODE: bool = os.getenv("PUBLIC_MODE", "true").lower() == "true"
    ALLOWED_USERS: List[int] = field(default_factory=list)
    BANNED_USERS: List[int] = field(default_factory=list)
    
    TELEGRAM_MODE: str = os.getenv("TELEGRAM_MODE", "business")
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/app.db")
    MEDIA_DIR: str = os.getenv("MEDIA_DIR", "data/media")
    
    SAVE_MODE_ENABLED: bool = os.getenv("SAVE_MODE_ENABLED", "true").lower() == "true"
    SAVE_MEDIA_ENABLED: bool = os.getenv("SAVE_MEDIA_ENABLED", "true").lower() == "true"
    MAX_MEDIA_SIZE_MB: int = int(os.getenv("MAX_MEDIA_SIZE_MB", 15))
    
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    
    CLEANUP_DAYS: int = int(os.getenv("CLEANUP_DAYS", 30))
    
    REQUIRED_CHANNEL_ID: int = int(os.getenv("REQUIRED_CHANNEL_ID", 0))
    REQUIRED_CHANNEL_URL: str = os.getenv("REQUIRED_CHANNEL_URL", "")
    
    REPEAT_DELAY_MIN_SECONDS: int = int(os.getenv("REPEAT_DELAY_MIN_SECONDS", 1))
    REPEAT_DELAY_MAX_SECONDS: int = int(os.getenv("REPEAT_DELAY_MAX_SECONDS", 3))
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")
    
    def __post_init__(self):
        allowed = os.getenv("ALLOWED_USERS", "")
        if allowed and allowed != "*":
            self.ALLOWED_USERS = [int(x.strip()) for x in allowed.split(",") if x.strip()]
        
        banned = os.getenv("BANNED_USERS", "")
        if banned:
            self.BANNED_USERS = [int(x.strip()) for x in banned.split(",") if x.strip()]


settings = Settings()