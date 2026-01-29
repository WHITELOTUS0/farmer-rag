"""
Application settings management using Pydantic Settings.

This module provides centralized configuration for all components of the
Farmer RAG Agent system, including LLM settings, database connections,
and feature flags.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Settings are loaded in the following order of precedence:
    1. Environment variables
    2. .env file
    3. Default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==================== OpenAI Configuration ====================
    openai_api_key: str = Field(
        ...,
        description="OpenAI API key for LLM and embedding access"
    )

    primary_model: str = Field(
        default="gpt-4o",
        description="Primary LLM model for reasoning and generation"
    )

    verification_model: str = Field(
        default="gpt-4o-mini",
        description="Model used for verification and groundedness checking"
    )

    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Model used for text embeddings"
    )

    model_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM responses (lower = more deterministic)"
    )

    # ==================== Database Configuration ====================
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/farmer_rag",
        description="Async PostgreSQL connection URL"
    )

    database_url_sync: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/farmer_rag",
        description="Sync PostgreSQL connection URL (for migrations)"
    )

    # ==================== ChromaDB Configuration ====================
    chroma_persist_directory: str = Field(
        default="./data/chroma",
        description="Directory for ChromaDB persistence"
    )

    chroma_collection_name: str = Field(
        default="agricultural_knowledge",
        description="Name of the ChromaDB collection"
    )

    # ==================== RAG Configuration ====================
    chunk_size: int = Field(
        default=800,
        ge=100,
        le=2000,
        description="Target size for document chunks (in tokens)"
    )

    chunk_overlap: int = Field(
        default=100,
        ge=0,
        le=500,
        description="Overlap between consecutive chunks"
    )

    retrieval_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of documents to retrieve"
    )

    confidence_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for retrieval results"
    )

    # ==================== Google Drive Configuration ====================
    google_drive_folder_id: Optional[str] = Field(
        default=None,
        description="Google Drive folder ID for document sync"
    )

    google_credentials_path: str = Field(
        default="./credentials.json",
        description="Path to Google OAuth credentials file"
    )

    # ==================== LangSmith Configuration ====================
    langchain_tracing_v2: bool = Field(
        default=False,
        description="Enable LangSmith tracing"
    )

    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        description="LangSmith API endpoint"
    )

    langchain_api_key: Optional[str] = Field(
        default=None,
        description="LangSmith API key"
    )

    langchain_project: str = Field(
        default="farmer-rag",
        description="LangSmith project name"
    )

    # ==================== Application Settings ====================
    app_env: str = Field(
        default="development",
        description="Application environment (development, staging, production)"
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    max_tool_calls_per_turn: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of tool calls allowed per agent turn"
    )

    max_verification_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retries if groundedness score is below threshold"
    )

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate that app_env is a valid environment."""
        valid_envs = {"development", "staging", "production"}
        if v.lower() not in valid_envs:
            raise ValueError(f"app_env must be one of {valid_envs}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate that log_level is a valid logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses lru_cache to ensure settings are only loaded once.
    Clear cache with get_settings.cache_clear() if needed.

    Returns:
        Settings: Application settings instance
    """
    return Settings()
