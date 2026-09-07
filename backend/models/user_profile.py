from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, Text
from sqlalchemy.sql import func
from database.connection import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True, nullable=False)

    # Personal Info
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    business_name = Column(String, nullable=True)
    business_role = Column(String, nullable=True)

    # Notification Preferences
    notify_escalation = Column(Boolean, default=True)
    notify_weekly_report = Column(Boolean, default=True)
    notify_new_conversation = Column(Boolean, default=True)
    notify_marketing_tips = Column(Boolean, default=False)
    notification_frequency = Column(String, default="instant")

    # Settings
    two_factor_enabled = Column(Boolean, default=False)
    theme = Column(String, default="light")
    timezone = Column(String, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())