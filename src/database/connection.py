"""
Database connection management for async and sync operations.

This module provides:
- Async session factory for FastAPI/async operations
- Sync session factory for migrations and scripts
- Database initialization function
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import get_settings
from src.database.models import Base

logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Create async engine for runtime operations
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,  # Log SQL in development
    pool_pre_ping=True,  # Verify connections before use
    pool_size=5,
    max_overflow=10,
)

# Create sync engine for migrations and scripts
sync_engine = create_engine(
    settings.database_url_sync,
    echo=settings.is_development,
    pool_pre_ping=True,
)

# Session factories
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """
    Initialize the database by creating all tables.

    This should be called once at application startup.
    For production, use Alembic migrations instead.
    """
    async with async_engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")


async def drop_db() -> None:
    """
    Drop all database tables.

    WARNING: This will delete all data. Use only in development/testing.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All database tables dropped")


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Usage:
        async with get_async_session() as session:
            result = await session.execute(query)

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection function for FastAPI.

    Usage in FastAPI:
        @app.get("/farmers")
        async def get_farmers(db: AsyncSession = Depends(get_db_session)):
            ...

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_session() -> Session:
    """
    Get a synchronous database session.

    Useful for scripts and migrations that don't need async.

    Returns:
        Session: SQLAlchemy sync session
    """
    return SyncSessionLocal()


async def check_db_connection() -> bool:
    """
    Check if the database connection is working.

    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        async with async_engine.connect() as conn:
            await conn.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
