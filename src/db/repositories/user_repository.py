from sqlalchemy import select
from typing import Optional
from src.db.models import User
from src.db.session import async_session


class UserRepository:
    """Репозиторий для работы с пользователями"""
    
    @staticmethod
    async def get_or_create(telegram_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
        """Получить пользователя или создать нового"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                if last_name:
                    user.last_name = last_name
                await session.commit()
                return user
            
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_active=True
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    @staticmethod
    async def get_by_id(telegram_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def update_settings(telegram_id: int, **kwargs) -> Optional[User]:
        """Обновить настройки пользователя"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            
            await session.commit()
            await session.refresh(user)
            return user