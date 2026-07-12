from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from server.database import Base
from server.utils.util import utc_now


class ConversationManagement(Base):
    """Legacy conversation snapshot table kept for database compatibility."""

    __tablename__ = "conversation_management"

    conversation_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    conversation_name = Column(String, nullable=True)
    created_time = Column(DateTime, default=utc_now)
    updated_time = Column(DateTime, default=utc_now, onupdate=utc_now)
    canvas = Column(String, nullable=True)
    messages = Column(String, nullable=True)


class ConversationSession(Base):
    """Session metadata persisted for the active local workflow."""

    __tablename__ = "conversation_sessions"

    session_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    first_message = Column(String(500), nullable=True)
    status = Column(String, default="active")
    error_message = Column(String, nullable=True)
    message_count = Column(Integer, default=0)
    step_count = Column(Integer, default=0)
    artifact_count = Column(Integer, default=0)
    prompt_tokens_total = Column(Integer, default=0)
    completion_tokens_total = Column(Integer, default=0)
    total_tokens_total = Column(Integer, default=0)
    llm_call_count = Column(Integer, default=0)
    prompt_text_tokens_total = Column(Integer, default=0)
    prompt_image_tokens_total = Column(Integer, default=0)
    prompt_video_tokens_total = Column(Integer, default=0)
    completion_text_tokens_total = Column(Integer, default=0)
    completion_image_tokens_total = Column(Integer, default=0)
    completion_video_tokens_total = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class ConversationMessage(Base):
    """Single persisted conversation event or assistant output."""

    __tablename__ = "conversation_messages"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    msg_type = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    artifacts = Column(Text, nullable=True)
    msg_metadata = Column(Text, nullable=True)
    sequence = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now)


class TokenUsageRecord(Base):
    """Token usage details for each tracked LLM call."""

    __tablename__ = "token_usage_records"

    id = Column(String, primary_key=True)
    event_id = Column(String, nullable=False, unique=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    component = Column(String, nullable=False)
    agent_name = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    prompt_text_tokens = Column(Integer, default=0)
    prompt_image_tokens = Column(Integer, default=0)
    prompt_video_tokens = Column(Integer, default=0)
    completion_text_tokens = Column(Integer, default=0)
    completion_image_tokens = Column(Integer, default=0)
    completion_video_tokens = Column(Integer, default=0)
    breakdown_available = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
