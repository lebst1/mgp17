from datetime import datetime, timedelta
from enum import Enum as PyEnum
import logging

from sqlalchemy import (
    Column, Integer, String, BigInteger, Boolean, DateTime, ForeignKey, Text,
    Index, Numeric, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from src.db.session import Base

logger = logging.getLogger(__name__)


class OrderStatus(PyEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class ReferralBonusStatus(PyEnum):
    HELD = "held"
    RELEASED = "released"
    CANCELLED = "cancelled"


class PaymentProvider(PyEnum):
    YOOKASSA = "yookassa"
    STRIPE = "stripe"
    STARS = "stars"  # 👈 ДОБАВЛЯЕМ


class TransactionType(PyEnum):
    SUBSCRIPTION = "subscription"
    REFERRAL_BONUS = "referral_bonus"
    REFUND = "refund"


class TransactionStatus(PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class User(Base):
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

    # savemode_enabled = Column(Boolean, default=False)
    autoreply_enabled = Column(Boolean, default=False)
    digest_enabled = Column(Boolean, default=False)
    digest_time = Column(String(10), default="09:00")

    messages_saved = Column(Integer, default=0)
    ai_requests = Column(Integer, default=0)

    subscription_until = Column(DateTime, nullable=True)

    referral_code = Column(String(64), unique=True, nullable=True, index=True)
    referred_by = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=True, index=True)

    referred_by_user = relationship(
        "User",
        remote_side=[telegram_id],
        foreign_keys=[referred_by],
        backref="direct_referrals",
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    saved_messages = relationship("SavedMessage", back_populates="user")
    todos = relationship("Todo", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")
    business_connections = relationship("BusinessConnection", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    transactions = relationship(
        "Transaction",
        back_populates="user",
        foreign_keys="Transaction.user_id",
    )
    bonuses_as_referrer = relationship(
        "ReferralBonus",
        back_populates="referrer",
        foreign_keys="ReferralBonus.referrer_id",
    )
    bonuses_as_referred = relationship(
        "ReferralBonus",
        back_populates="referred_user",
        foreign_keys="ReferralBonus.referred_id",
    )

    __table_args__ = (
        Index("ix_users_referred_by", "referred_by"),
    )

    def has_active_subscription(self) -> bool:
        if self.subscription_until is None:
            return False
        return self.subscription_until > datetime.utcnow()

    def extend_subscription(self, days: int) -> datetime:
        now = datetime.utcnow()
        if self.subscription_until and self.subscription_until > now:
            self.subscription_until = self.subscription_until + timedelta(days=days)
        else:
            self.subscription_until = now + timedelta(days=days)
        return self.subscription_until

    def get_subscription_info(self) -> dict:
        now = datetime.utcnow()
        is_active = self.has_active_subscription()
        days_left = 0
        if self.subscription_until and self.subscription_until > now:
            days_left = (self.subscription_until - now).days
        return {
            "is_active": is_active,
            "subscription_until": self.subscription_until,
            "days_left": days_left,
            "status": "✅ Активна" if is_active else "❌ Истекла",
        }

    def __repr__(self):
        return f"<User {self.telegram_id} ({self.username or self.first_name})>"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    payment_id = Column(String(255), unique=True, nullable=False, index=True)
    provider = Column(SAEnum(PaymentProvider, name="payment_provider_enum"), nullable=False, default=PaymentProvider.YOOKASSA)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="RUB")
    status = Column(SAEnum(OrderStatus, name="order_status_enum"), nullable=False, default=OrderStatus.PENDING)
    description = Column(String(500), nullable=True)
    provider_raw = Column(Text, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="payments")
    transactions = relationship("Transaction", back_populates="payment")

    __table_args__ = (
        Index("ix_payments_user_id_status", "user_id", "status"),
        Index("ix_payments_created_at", "created_at"),
    )

    @property
    def is_successful(self) -> bool:
        return self.status == OrderStatus.PAID

    def __repr__(self):
        return f"<Payment {self.payment_id} {self.status.value}>"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    type = Column(SAEnum(TransactionType, name="transaction_type_enum"), nullable=False)
    status = Column(SAEnum(TransactionStatus, name="transaction_status_enum"), nullable=False, default=TransactionStatus.PENDING)
    amount = Column(Numeric(12, 2), nullable=True)
    days_credited = Column(Integer, nullable=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)
    referral_bonus_id = Column(Integer, ForeignKey("referral_bonuses.id"), nullable=True, index=True)
    reference_id = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)
    metadata_ = Column("metadata", Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="transactions")
    payment = relationship("Payment", back_populates="transactions")
    referral_bonus = relationship("ReferralBonus", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_user_type_status", "user_id", "type", "status"),
        Index("ix_transactions_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Transaction id={self.id} type={self.type.value} status={self.status.value}>"


class ReferralBonus(Base):
    __tablename__ = "referral_bonuses"

    id = Column(Integer, primary_key=True)
    referrer_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    referred_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    status = Column(SAEnum(ReferralBonusStatus, name="referral_bonus_status_enum"), nullable=False, default=ReferralBonusStatus.HELD)
    referrer_days = Column(Integer, nullable=False, default=0)
    referred_days = Column(Integer, nullable=False, default=0)
    triggered_by_payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)
    released_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    referrer = relationship(
        "User",
        back_populates="bonuses_as_referrer",
        foreign_keys=[referrer_id],
    )
    referred_user = relationship(
        "User",
        back_populates="bonuses_as_referred",
        foreign_keys=[referred_id],
    )
    triggered_by_payment = relationship("Payment", foreign_keys=[triggered_by_payment_id])
    transactions = relationship("Transaction", back_populates="referral_bonus")

    __table_args__ = (
        UniqueConstraint("referred_id", name="uq_referral_bonuses_referred_id"),
        Index("ix_referral_bonuses_referrer_status", "referrer_id", "status"),
        Index("ix_referral_bonuses_created_at", "created_at"),
    )

    def __repr__(self):
        return (
            f"<ReferralBonus id={self.id} referrer={self.referrer_id} "
            f"referred={self.referred_id} status={self.status.value}>"
        )


class BusinessConnection(Base):
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
        Index("ix_business_connections_user_id", "user_id"),
    )

    def __repr__(self):
        return f"<BusinessConnection {self.connection_id} for user {self.user_id}>"


class SavedMessage(Base):
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
        Index("ix_saved_messages_user_id", "user_id"),
        Index("ix_saved_messages_chat_id", "chat_id"),
        Index("ix_saved_messages_is_deleted", "is_deleted"),
        Index("ix_saved_messages_saved_at", "saved_at"),
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

    # __table_args__ = (
    #     Index("ix_todos_user_id", "user_id"),
    #     Index("ix_todos_is_done", "is_done"),
    # )


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
        Index("ix_reminders_user_id", "user_id"),
        Index("ix_reminders_remind_at", "remind_at"),
        Index("ix_reminders_is_done", "is_done"),
    )
