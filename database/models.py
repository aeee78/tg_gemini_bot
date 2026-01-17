from sqlalchemy import Column, Integer, String, Boolean, Text, BigInteger, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from database.db import Base
from constants import DEFAULT_MODEL, SEND_MODE_IMMEDIATE

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)  # Telegram User ID
    current_model = Column(String, default=DEFAULT_MODEL)
    send_mode = Column(String, default=SEND_MODE_IMMEDIATE)
    search_enabled = Column(Boolean, default=False)

    # Relationships
    chat_session = relationship("ChatSession", back_populates="user", uselist=False)
    file_contexts = relationship("FileContext", back_populates="user")
    message_buffer = relationship("MessageBuffer", back_populates="user")

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    history_json = Column(Text, default="[]")  # JSON serialized list of contents

    user = relationship("User", back_populates="chat_session")

class FileContext(Base):
    __tablename__ = "file_contexts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    filename = Column(String)
    mime_type = Column(String)
    data = Column(LargeBinary) # Storing file bytes
    caption = Column(Text, nullable=True)

    user = relationship("User", back_populates="file_contexts")

class MessageBuffer(Base):
    __tablename__ = "message_buffers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    item_type = Column(String) # "text", "photo", "document"

    content = Column(Text, nullable=True) # Text content or caption
    blob_data = Column(LargeBinary, nullable=True) # Image or file bytes
    filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)

    user = relationship("User", back_populates="message_buffer")
