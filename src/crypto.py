import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config import settings

logger = logging.getLogger(__name__)


def get_encryption_key() -> bytes:
    """Получает или генерирует ключ шифрования из settings"""
    key = settings.ENCRYPTION_KEY
    if not key:
        # Если ключа нет, генерируем новый
        key = Fernet.generate_key().decode()
        logger.warning("⚠️ ENCRYPTION_KEY не задан в .env, сгенерирован временный ключ")
        logger.warning(f"📌 Добавьте в .env: ENCRYPTION_KEY={key}")
    return key.encode()


def encrypt_secret(secret: str) -> str:
    """Шифрует секрет"""
    if not secret:
        return ""
    try:
        key = get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(secret.encode())
        return base64.b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"❌ Ошибка шифрования: {e}")
        return secret


def decrypt_secret(encrypted: str) -> str:
    """Расшифровывает секрет"""
    if not encrypted:
        return ""
    try:
        key = get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(base64.b64decode(encrypted))
        return decrypted.decode()
    except Exception as e:
        logger.error(f"❌ Ошибка расшифровки: {e}")
        return ""