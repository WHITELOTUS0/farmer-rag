"""
SQLAlchemy models for the Farmer RAG Agent database.

This module defines the database schema for storing:
- User profiles and contact information
- Farm details and locations
- Crop planting and growth stage tracking
- Advisory history with groundedness scores
- System configuration for admin settings
- Document metadata for ingested files
"""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class CropType(str, enum.Enum):
    """Enumeration of supported crop types."""
    MAIZE = "maize"
    BEANS = "beans"
    TOMATOES = "tomatoes"


class GrowthStage(str, enum.Enum):
    """Enumeration of crop growth stages."""
    PLANTING = "planting"
    GERMINATION = "germination"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    MATURITY = "maturity"
    HARVEST = "harvest"


class DocumentStatus(str, enum.Enum):
    """Status of document processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UserRole(str, enum.Enum):
    """Role for authenticated users."""
    ADMIN = "admin"
    FARMER = "farmer"


class JobStatus(str, enum.Enum):
    """Background job status."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Farm(Base):
    """
    Farm entity representing a specific plot of land.

    A farmer can have multiple farms, each with different crops
    and soil characteristics.
    """
    __tablename__ = "farms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_hectares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    soil_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Location (can be different from farmer's home location)
    location_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Additional metadata
    irrigation_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    crops: Mapped[List["Crop"]] = relationship(
        "Crop",
        back_populates="farm",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Farm(id={self.id}, name='{self.name}', size={self.size_hectares}ha)>"


class Crop(Base):
    """
    Crop instance representing a specific planting on a farm.

    Tracks the lifecycle of a crop from planting to harvest,
    enabling growth-stage-specific recommendations.
    """
    __tablename__ = "crops"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    farm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("farms.id", ondelete="CASCADE"),
        nullable=False
    )

    crop_type: Mapped[CropType] = mapped_column(
        SQLEnum(CropType),
        nullable=False
    )
    variety: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Growth tracking
    planting_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    current_growth_stage: Mapped[GrowthStage] = mapped_column(
        SQLEnum(GrowthStage),
        default=GrowthStage.PLANTING,
        nullable=False
    )
    expected_harvest_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    actual_harvest_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    # Yield tracking
    expected_yield_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_yield_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Area planted
    area_hectares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    farm: Mapped["Farm"] = relationship("Farm", back_populates="crops")

    def __repr__(self) -> str:
        return f"<Crop(id={self.id}, type={self.crop_type.value}, stage={self.current_growth_stage.value})>"


class Advisory(Base):
    """
    Advisory record storing generated recommendations and their verification.

    Each advisory includes the full context of what was retrieved,
    the groundedness score, and whether the farmer acknowledged it.
    """
    __tablename__ = "advisories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # The query and response
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)

    # Verification data
    groundedness_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )
    sources: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
    )  # [{source_id, chunk_text, confidence}]

    # Tool usage tracking
    tools_used: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
    )  # [{tool_name, input, output}]

    # Verification details
    claims_verified: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
    )  # [{claim, supported, source_id}]

    # User interaction
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    farmer_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Advisory(id={self.id}, score={self.groundedness_score:.2f})>"


class SystemConfig(Base):
    """
    System configuration storage for admin-adjustable settings.

    Stores key-value pairs for settings like model temperature,
    confidence thresholds, and feature flags.
    """
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<SystemConfig(key='{self.key}')>"


class Document(Base):
    """
    Document metadata for tracking ingested files.

    Stores information about source documents used in the RAG system,
    including their processing status and chunk count.
    """
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Source information
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # pdf, docx, txt
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Google Drive URL
    drive_file_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Processing status
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Content metadata (extracted during processing)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True
    )  # {crop_types, topics, page_count, etc.}

    # File info
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA-256

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.filename}', status={self.status.value})>"


class User(Base):
    """
    Authenticated user (mirrors Supabase auth.users).
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.FARMER,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class UserProfile(Base):
    """
    Extended profile for a user.
    """
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    location_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="profile")


class Conversation(Base):
    """
    Conversation container for a user.
    """
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Message(Base):
    """
    Message within a conversation.
    """
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ToolCall(Base):
    """
    Tool calls associated with a conversation.
    """
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_input: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DocumentChunk(Base):
    """
    Vectorized document chunk for pgvector retrieval.
    """
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=False)
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class BackgroundJob(Base):
    """
    Background job tracking for async processing.
    """
    __tablename__ = "background_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus),
        default=JobStatus.QUEUED,
        nullable=False,
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_after: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class EvaluationRun(Base):
    """
    Stored evaluation run results for tracking agent performance over time.
    """
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)  # Summary statistics
    results: Mapped[dict] = mapped_column(JSON, nullable=False)  # Detailed test results
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
