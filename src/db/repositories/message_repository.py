from sqlalchemy import select, desc, and_, or_
from typing import List, Optional
from src.db.models import SavedMessage
from src.db.session import async_session


class MessageRepository:
    @staticmethod
    async def save_message(data: dict) -> SavedMessage:
        async with async_session() as session:
            message = SavedMessage(**data)
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message
    
    @staticmethod
    async def get_recent_deleted(user_id: int, limit: int = 10) -> List[SavedMessage]:
        async with async_session() as session:
            result = await session.execute(
                select(SavedMessage)
                .where(
                    and_(
                        SavedMessage.user_id == user_id,
                        SavedMessage.is_deleted == True
                    )
                )
                .order_by(desc(SavedMessage.saved_at))
                .limit(limit)
            )
            return result.scalars().all()
    
    @staticmethod
    async def search_messages(user_id: int, query: str, limit: int = 10) -> List[SavedMessage]:
        async with async_session() as session:
            result = await session.execute(
                select(SavedMessage)
                .where(
                    and_(
                        SavedMessage.user_id == user_id,
                        or_(
                            SavedMessage.text.ilike(f"%{query}%"),
                            SavedMessage.from_username.ilike(f"%{query}%"),
                            SavedMessage.chat_title.ilike(f"%{query}%")
                        )
                    )
                )
                .order_by(desc(SavedMessage.saved_at))
                .limit(limit)
            )
            return result.scalars().all()
    
    @staticmethod
    async def mark_as_deleted(message_id: int, chat_id: int, user_id: int) -> Optional[SavedMessage]:
        async with async_session() as session:
            result = await session.execute(
                select(SavedMessage)
                .where(
                    and_(
                        SavedMessage.message_id == message_id,
                        SavedMessage.chat_id == chat_id,
                        SavedMessage.user_id == user_id
                    )
                )
            )
            message = result.scalar_one_or_none()
            
            if message:
                message.is_deleted = True
                await session.commit()
                await session.refresh(message)
            
            return message
    
    @staticmethod
    async def get_by_id(message_id: int, user_id: int) -> Optional[SavedMessage]:
        async with async_session() as session:
            result = await session.execute(
                select(SavedMessage)
                .where(
                    and_(
                        SavedMessage.id == message_id,
                        SavedMessage.user_id == user_id
                    )
                )
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_id_and_chat(message_id: int, chat_id: int, user_id: int) -> Optional[SavedMessage]:
        async with async_session() as session:
            result = await session.execute(
                select(SavedMessage)
                .where(
                    and_(
                        SavedMessage.message_id == message_id,
                        SavedMessage.chat_id == chat_id,
                        SavedMessage.user_id == user_id
                    )
                )
            )
            return result.scalar_one_or_none()