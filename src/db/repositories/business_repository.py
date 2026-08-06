from sqlalchemy import select
from typing import Optional, List
from datetime import datetime
from src.db.models import BusinessConnection, User
from src.db.session import async_session
import logging

logger = logging.getLogger(__name__)


class BusinessRepository:
    """Репозиторий для работы с бизнес-подключениями"""
    
    @staticmethod
    async def save_connection(connection_id: str, user_telegram_id: int, is_enabled: bool = True) -> BusinessConnection:
        async with async_session() as session:
            result = await session.execute(
                select(BusinessConnection).where(
                    BusinessConnection.connection_id == connection_id
                )
            )
            connection = result.scalar_one_or_none()
            
            if connection:
                connection.is_enabled = is_enabled
                connection.last_activity = datetime.utcnow()
                connection.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(connection)
                return connection
            
            connection = BusinessConnection(
                connection_id=connection_id,
                user_id=user_telegram_id,
                is_enabled=is_enabled,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_activity=datetime.utcnow()
            )
            session.add(connection)
            await session.commit()
            await session.refresh(connection)
            return connection
    
    @staticmethod
    async def get_user_by_connection(connection_id: str) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User)
                .join(BusinessConnection, User.telegram_id == BusinessConnection.user_id)
                .where(BusinessConnection.connection_id == connection_id)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def get_connection(connection_id: str) -> Optional[BusinessConnection]:
        async with async_session() as session:
            result = await session.execute(
                select(BusinessConnection).where(
                    BusinessConnection.connection_id == connection_id
                )
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def get_or_create_connection_by_user(connection_id: str, user_id: int) -> BusinessConnection:
        async with async_session() as session:
            result = await session.execute(
                select(BusinessConnection).where(
                    BusinessConnection.connection_id == connection_id
                )
            )
            connection = result.scalar_one_or_none()
            
            if connection:
                return connection
            
            logger.info(f"💾 Создаем новый connection_id: {connection_id} для пользователя {user_id}")
            connection = BusinessConnection(
                connection_id=connection_id,
                user_id=user_id,
                is_enabled=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_activity=datetime.utcnow()
            )
            session.add(connection)
            await session.commit()
            await session.refresh(connection)
            return connection
    
    @staticmethod
    async def update_activity(connection_id: str):
        async with async_session() as session:
            result = await session.execute(
                select(BusinessConnection).where(
                    BusinessConnection.connection_id == connection_id
                )
            )
            connection = result.scalar_one_or_none()
            if connection:
                connection.last_activity = datetime.utcnow()
                connection.updated_at = datetime.utcnow()
                await session.commit()
    
    @staticmethod
    async def get_user_connections(user_telegram_id: int) -> List[BusinessConnection]:
        async with async_session() as session:
            result = await session.execute(
                select(BusinessConnection).where(
                    BusinessConnection.user_id == user_telegram_id
                )
            )
            return result.scalars().all()