from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, ForeignKey, Text, Index
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
    
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    can_use_savemode = Column(Boolean, default=True)
    can_use_ai = Column(Boolean, default=True)
    can_use_dot_commands = Column(Boolean, default=True)
    
    savemode_enabled = Column(Boolean, default=True)
    autoreply_enabled = Column(Boolean, default=False)
    digest_enabled = Column(Boolean, default=False)
    digest_time = Column(String(10), default="09:00")
    
    messages_saved = Column(Integer, default=0)
    ai_requests = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    saved_messages = relationship("SavedMessage", back_populates="user")
    todos = relationship("Todo", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")
    business_connections = relationship("BusinessConnection", back_populates="user")
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    
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
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="business_connections")
    
    __table_args__ = (
        Index('ix_business_connections_user_id', 'user_id'),
    )
    
    def __repr__(self):
        return f"<BusinessConnection {self.connection_id} for user {self.user_id}>"


class SavedMessage(Base):
    """Сохраненное сообщение"""
    __tablename__ = "saved_messages"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    connection_id = Column(String(255), nullable=True, index=True)
    
    chat_id = Column(BigInteger, nullable=False, index=True)
    chat_title = Column(String(255), nullable=True)
    message_id = Column(Integer, nullable=False)
    from_user_id = Column(BigInteger, nullable=True)
    from_username = Column(String(255), nullable=True)
    from_first_name = Column(String(255), nullable=True)
    
    text = Column(Text, nullable=True)
    media_type = Column(String(50), nullable=True)
    media_file_id = Column(String(255), nullable=True)
    media_path = Column(String(500), nullable=True)
    media_size = Column(Integer, nullable=True)
    
    is_deleted = Column(Boolean, default=False, index=True)
    is_edited = Column(Boolean, default=False)
    edit_history = Column(Text, nullable=True)
    
    saved_at = Column(DateTime, default=datetime.utcnow)
    original_date = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="saved_messages")
    
    __table_args__ = (
        Index('ix_saved_messages_user_id', 'user_id'),
        Index('ix_saved_messages_chat_id', 'chat_id'),
        Index('ix_saved_messages_is_deleted', 'is_deleted'),
        Index('ix_saved_messages_saved_at', 'saved_at'),
    )
    
    def __repr__(self):
        return f"<SavedMessage {self.id} from chat {self.chat_id}>"


class Todo(Base):
    __tablename__ = "todos"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    is_done = Column(Boolean, default=False)
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="todos")
    
    __table_args__ = (
        Index('ix_todos_user_id', 'user_id'),
        Index('ix_todos_is_done', 'is_done'),
    )


class Reminder(Base):
    __tablename__ = "reminders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    remind_at = Column(DateTime, nullable=False)
    is_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="reminders")
    
    __table_args__ = (
        Index('ix_reminders_user_id', 'user_id'),
        Index('ix_reminders_remind_at', 'remind_at'),
        Index('ix_reminders_is_done', 'is_done'),
    )


class Subscription(Base):
    """Модель подписки пользователя"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, unique=True, index=True)
    
    subscription_type = Column(String(50), default="trial")
    
    starts_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    trial_used = Column(Boolean, default=False)
    
    is_active = Column(Boolean, default=True)
    auto_renew = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="subscription")
    
    __table_args__ = (
        Index('ix_subscriptions_user_id', 'user_id'),
        Index('ix_subscriptions_expires_at', 'expires_at'),
        Index('ix_subscriptions_is_active', 'is_active'),
    )


# Добавляем связи в User
User.saved_messages = relationship("SavedMessage", back_populates="user")
User.todos = relationship("Todo", back_populates="user")
User.reminders = relationship("Reminder", back_populates="user")
User.business_connections = relationship("BusinessConnection", back_populates="user")
User.subscription = relationship("Subscription", back_populates="user", uselist=False)