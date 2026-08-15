"""[B14] SQLAlchemy ORM models — literal translation of the DDL in CLAUDE.md
§3. Schema declarations only; no I/O happens on import.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_id = Column(Text, unique=True, nullable=False)
    email = Column(Text, unique=True)
    name = Column(Text)
    avatar_url = Column(Text)
    plan = Column(Text, default="free")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_users_clerk_id", "clerk_id"),
        Index("idx_users_email", "email"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, default="New Conversation")
    summary = Column(Text)  # [B3] never written, never read in v1
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    last_message_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_conversations_user_id", "user_id"),
        Index("idx_conversations_updated_at", updated_at.desc()),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # [A1] denormalized for cross-conversation vector search
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384))
    emotional_tone = Column(Text)
    tokens_used = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="messages_role_check"),
        Index("idx_messages_conversation_id", "conversation_id"),
        Index("idx_messages_user_id", "user_id"),
        Index("idx_messages_created_at", created_at.desc()),
        Index("idx_messages_embedding", embedding, postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )


class UserFact(Base):
    __tablename__ = "user_facts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject = Column(Text, nullable=False, default="User")
    predicate = Column(Text, nullable=False)
    object = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    archived_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "subject", "predicate", "object", name="user_facts_unique"),
        Index("idx_user_facts_user_id", "user_id"),
        Index("idx_user_facts_active", "user_id", postgresql_where=(is_active == True)),  # noqa: E712
        Index("idx_user_facts_predicate", "predicate"),
    )


class SessionState(Base):
    __tablename__ = "session_state"

    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    turn_count = Column(Integer, default=0)
    current_persona = Column(Text)
    pending_persona = Column(Text)
    last_3_messages = Column(JSONB)  # [B2] holds 6 entries (3 turns), sliced [-6:]
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_session_state_user_id", "user_id"),)
