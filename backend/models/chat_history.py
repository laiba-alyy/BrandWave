from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from database.connection import Base


class AssistantChatSession(Base):
    __tablename__ = "assistant_chat_sessions"

    id = Column(String, primary_key=True)          # session_id (UUID, frontend se aata hai)
    user_id = Column(String, index=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class AssistantChatMessage(Base):
    __tablename__ = "assistant_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    session_id = Column(String, index=True)
    current_page = Column(String, nullable=True)
    sender = Column(String)
    message = Column(Text)
    created_at = Column(DateTime, default=func.now())