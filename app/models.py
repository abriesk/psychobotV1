# app/models.py - v1.0.2 with Notification Queue
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, BigInteger, Text, ForeignKey, DateTime, Enum, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from app.db import Base
import enum

# ============================================================================
# ENUMS
# ============================================================================

class RequestType(enum.Enum):
    WAITLIST = "waitlist"
    INDIVIDUAL = "individual"
    COUPLE = "couple"

class RequestStatus(enum.Enum):
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELED = "canceled"

class SenderType(enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"

class SlotStatus(enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"
    HELD = "held"

class NotificationType(enum.Enum):
    """Types of notifications the bot can send"""
    PROPOSAL = "proposal"           # Admin proposes time to client
    CONFIRMATION = "confirmation"   # Booking confirmed
    REJECTION = "rejection"         # Booking rejected
    REMINDER = "reminder"           # Upcoming session reminder
    CUSTOM = "custom"               # Custom message

# ============================================================================
# CORE TABLES
# ============================================================================

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True)
    language = Column(String(2), default='ru')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    requests = relationship("Request", back_populates="user")

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    availability_on = Column(Boolean, default=True)
    
    individual_price = Column(String, default="50 USD / 60 min")
    couple_price = Column(String, default="70 USD / 60 min")
    
    auto_confirm_slots = Column(Boolean, default=False)
    reminder_24h_enabled = Column(Boolean, default=True)
    reminder_1h_enabled = Column(Boolean, default=True)
    cancel_window_hours = Column(Integer, default=24)

# ============================================================================
# v1.0 NEW: TRANSLATION SYSTEM
# ============================================================================

class Translation(Base):
    __tablename__ = 'translations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    lang = Column(String(2), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(Text, nullable=False)
    
    __table_args__ = (UniqueConstraint('lang', 'key', name='uix_lang_key'),)

# ============================================================================
# v1.0 NEW: SLOT SYSTEM
# ============================================================================

class Slot(Base):
    __tablename__ = 'slots'
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    
    is_online = Column(Boolean, default=True)
    status = Column(Enum(SlotStatus), default=SlotStatus.AVAILABLE, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    requests = relationship(
        "Request", 
        back_populates="slot",
        foreign_keys="[Request.slot_id]"
    )

# ============================================================================
# EXTENDED: REQUEST TABLE
# ============================================================================

class Request(Base):
    __tablename__ = 'requests'
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_uuid = Column(String, unique=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(BigInteger, ForeignKey('users.id'))
    
    type = Column(Enum(RequestType))
    onsite = Column(Boolean, nullable=True)
    timezone = Column(String, nullable=True)
    desired_time = Column(String, nullable=True)
    problem = Column(Text, nullable=True)
    address_name = Column(String, nullable=True)
    preferred_comm = Column(String, nullable=True)
    
    status = Column(Enum(RequestStatus), default=RequestStatus.PENDING)
    final_time = Column(String, nullable=True)
    
    # v1.0: Slot-based scheduling
    slot_id = Column(Integer, ForeignKey('slots.id'), nullable=True)
    scheduled_datetime = Column(DateTime, nullable=True)
    
    # v1.0: Reminder tracking
    reminder_24h_sent = Column(Boolean, default=False)
    reminder_1h_sent = Column(Boolean, default=False)
    reminders_log = Column(JSON, nullable=True)
    
    # v1.0: Cancellation tracking
    cancelled_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="requests")
    negotiations = relationship("Negotiation", back_populates="request")
    slot = relationship(
        "Slot", 
        back_populates="requests",
        foreign_keys=[slot_id]
    )
    notifications = relationship("PendingNotification", back_populates="request")

# ============================================================================
# NEGOTIATION HISTORY
# ============================================================================

class Negotiation(Base):
    __tablename__ = 'negotiations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey('requests.id'))
    sender = Column(Enum(SenderType))
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    request = relationship("Request", back_populates="negotiations")

# ============================================================================
# v1.0.2 NEW: TELEGRAM NOTIFICATION QUEUE
# ============================================================================

class PendingNotification(Base):
    """
    Queue for notifications that web UI wants bot to send.
    Bot polls this table and sends Telegram messages.
    """
    __tablename__ = 'pending_notifications'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Target user
    user_id = Column(BigInteger, nullable=False, index=True)  # Telegram user ID
    
    # Related request (optional)
    request_id = Column(Integer, ForeignKey('requests.id'), nullable=True)
    
    # Notification content
    notification_type = Column(Enum(NotificationType), nullable=False)
    message = Column(Text, nullable=False)  # Message to send
    
    # For proposals: store the proposed time so bot can create buttons
    proposed_time = Column(String, nullable=True)
    
    # Status tracking
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    sent_at = Column(DateTime, nullable=True, index=True)  # NULL = pending, set = sent
    error = Column(Text, nullable=True)  # Error message if send failed
    attempts = Column(Integer, default=0)  # Retry counter
    
    # Relationship
    request = relationship("Request", back_populates="notifications")
# ============================================================================
# v1.1 NEW: TIMEZONE MANAGEMENT
# ============================================================================

class Timezone(Base):
    """
    Admin-configurable timezones for client selection.
    Replaces hardcoded timezone dropdowns/text input.
    """
    __tablename__ = 'timezones'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    offset_str = Column(String(10), unique=True, nullable=False)  # "UTC+4", "UTC-5"
    offset_minutes = Column(Integer, nullable=False)  # 240, -300 (for calculations)
    display_name = Column(String(100), nullable=False)  # "Yerevan, Dubai (Armenia/UAE)"
    is_active = Column(Boolean, default=True, index=True)
    sort_order = Column(Integer, default=0)  # For custom ordering
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Timezone {self.offset_str}: {self.display_name}>"


# ============================================================================
# DEFAULT TIMEZONE DATA (for seeding)
# ============================================================================

DEFAULT_TIMEZONES = [
    {"offset_str": "UTC+4", "offset_minutes": 240, "display_name": "Yerevan, Dubai, Baku", "sort_order": 1},
    {"offset_str": "UTC+3", "offset_minutes": 180, "display_name": "Moscow, Istanbul, Minsk", "sort_order": 2},
    {"offset_str": "UTC+2", "offset_minutes": 120, "display_name": "Kyiv, Athens, Helsinki", "sort_order": 3},
    {"offset_str": "UTC+1", "offset_minutes": 60, "display_name": "Berlin, Paris, Rome", "sort_order": 4},
    {"offset_str": "UTC+0", "offset_minutes": 0, "display_name": "London, Lisbon, Dublin", "sort_order": 5},
    {"offset_str": "UTC-5", "offset_minutes": -300, "display_name": "New York, Toronto, Miami", "sort_order": 6},
    {"offset_str": "UTC-8", "offset_minutes": -480, "display_name": "Los Angeles, Vancouver", "sort_order": 7},
]