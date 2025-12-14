from sqlalchemy import Column, Integer, String, Boolean, Text, BigInteger, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.core import Base
from app.config import config

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True)

    current_model = Column(String, default=config.DEFAULT_MODEL)
    send_mode = Column(String, default=config.SEND_MODE_IMMEDIATE)
    search_enabled = Column(Boolean, default=False)
    is_whitelisted = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    file_contexts = relationship("FileContext", back_populates="user", cascade="all, delete-orphan")
    buffer_items = relationship("BufferItem", back_populates="user", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String) # 'user' or 'model'
    content = Column(Text) # Plain text content
    has_images = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="messages")

class FileContext(Base):
    __tablename__ = "file_contexts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_id = Column(String) # Telegram File ID
    file_unique_id = Column(String) # Unique ID to prevent duplicates if needed
    file_name = Column(String)
    mime_type = Column(String)
    caption = Column(Text, nullable=True)
    local_path = Column(String, nullable=True) # If we download and store locally (optional)

    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="file_contexts")

class BufferItem(Base):
    __tablename__ = "buffer_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_type = Column(String) # 'text', 'photo', 'document'
    content = Column(Text) # Text content or File ID
    caption = Column(Text, nullable=True)
    mime_type = Column(String, nullable=True) # For docs
    file_name = Column(String, nullable=True) # For docs

    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="buffer_items")
