from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from src.db.session import Base


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    
    # Права доступа
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    can_use_savemode = Column(Boolean, default=True)
    can_use_ai = Column(Boolean, default=True)
    can_use_dot_commands = Column(Boolean, default=True)
    
    # Настройки пользователя
    savemode_enabled = Column(Boolean, default=True)
    autoreply_enabled = Column(Boolean, default=False)
    digest_enabled = Column(Boolean, default=False)
    digest_time = Column(String(10), default="09:00")
    
    # Статистика
    messages_saved = Column(Integer, default=0)
    ai_requests = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    saved_messages = relationship("SavedMessage", back_populates="user")
    todos = relationship("Todo", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")
    business_connections = relationship("BusinessConnection", back_populates="user")
    
    def __repr__(self):
        return f"<User {self.telegram_id} ({self.username or self.first_name})>"


class BusinessConnection(Base):
    """Модель бизнес-подключения"""
    __tablename__ = "business_connections"
    
    id = Column(Integer, primary_key=True)
    connection_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    
    is_enabled = Column(Boolean, default=True)
    can_reply = Column(Boolean, default=False)
    
    connected_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="business_connections")
    
    def __repr__(self):
        return f"<BusinessConnection {self.connection_id} for user {self.user_id}>"


class SavedMessage(Base):
    """Сохраненное сообщение"""
    __tablename__ = "saved_messages"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    connection_id = Column(String(255), nullable=True, index=True)
    
    # Информация о сообщении
    chat_id = Column(BigInteger, nullable=False, index=True)
    chat_title = Column(String(255), nullable=True)
    message_id = Column(Integer, nullable=False)
    from_user_id = Column(BigInteger, nullable=True)
    from_username = Column(String(255), nullable=True)
    from_first_name = Column(String(255), nullable=True)
    
    # Содержимое
    text = Column(Text, nullable=True)
    media_type = Column(String(50), nullable=True)
    media_file_id = Column(String(255), nullable=True)
    media_path = Column(String(500), nullable=True)
    media_size = Column(Integer, nullable=True)
    
    # Метаданные
    is_deleted = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    edit_history = Column(Text, nullable=True)
    
    saved_at = Column(DateTime, default=datetime.utcnow)
    original_date = Column(DateTime, nullable=True)
    
    # Связи
    user = relationship("User", back_populates="saved_messages")
    
    def __repr__(self):
        return f"<SavedMessage {self.id} from chat {self.chat_id}>"


class Todo(Base):
    """Задача пользователя"""
    __tablename__ = "todos"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    is_done = Column(Boolean, default=False)
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="todos")


class Reminder(Base):
    """Напоминание пользователя"""
    __tablename__ = "reminders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    remind_at = Column(DateTime, nullable=False)
    is_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="reminders")


# Добавляем связи в User
User.saved_messages = relationship("SavedMessage", back_populates="user")
User.todos = relationship("Todo", back_populates="user")
User.reminders = relationship("Reminder", back_populates="user")
User.business_connections = relationship("BusinessConnection", back_populates="user")