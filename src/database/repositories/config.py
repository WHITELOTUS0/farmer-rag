"""
Repository for System Configuration database operations.

Handles admin-adjustable settings stored in the database,
allowing runtime configuration changes without redeployment.
"""

from typing import Optional, List, Any

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import SystemConfig


class ConfigRepository:
    """Repository for system configuration operations."""

    def __init__(self, session: AsyncSession):
        """
        Initialize the repository with a database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_config(self, key: str) -> Optional[Any]:
        """
        Get a configuration value by key.

        Args:
            key: Configuration key

        Returns:
            Configuration value or None if not found
        """
        query = select(SystemConfig).where(SystemConfig.key == key)
        result = await self.session.execute(query)
        config = result.scalar_one_or_none()
        return config.value if config else None

    async def set_config(
        self,
        key: str,
        value: Any,
        description: Optional[str] = None,
    ) -> SystemConfig:
        """
        Set a configuration value (insert or update).

        Args:
            key: Configuration key
            value: Configuration value (will be stored as JSON)
            description: Optional description of the setting

        Returns:
            SystemConfig: The created/updated configuration
        """
        # Use PostgreSQL upsert
        stmt = insert(SystemConfig).values(
            key=key,
            value=value,
            description=description,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[SystemConfig.key],
            set_={
                "value": value,
                "description": description if description else stmt.excluded.description,
            },
        )
        await self.session.execute(stmt)

        # Fetch and return the config
        return await self.get_config_obj(key)

    async def get_config_obj(self, key: str) -> Optional[SystemConfig]:
        """
        Get the full SystemConfig object by key.

        Args:
            key: Configuration key

        Returns:
            SystemConfig or None if not found
        """
        query = select(SystemConfig).where(SystemConfig.key == key)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all_configs(self) -> List[SystemConfig]:
        """
        Get all system configurations.

        Returns:
            List of all SystemConfig instances
        """
        query = select(SystemConfig).order_by(SystemConfig.key)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_config(self, key: str) -> bool:
        """
        Delete a configuration by key.

        Args:
            key: Configuration key to delete

        Returns:
            True if deleted, False if not found
        """
        stmt = delete(SystemConfig).where(SystemConfig.key == key)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def get_model_settings(self) -> dict:
        """
        Get all model-related settings as a dictionary.

        Returns:
            Dictionary with model settings
        """
        defaults = {
            "primary_model": "gpt-4o",
            "verification_model": "gpt-4o-mini",
            "embedding_model": "text-embedding-3-small",
            "temperature": 0.3,
            "confidence_threshold": 0.80,
            "max_tool_calls": 5,
        }

        # Override with database values
        for key in defaults.keys():
            db_value = await self.get_config(f"model_{key}")
            if db_value is not None:
                defaults[key] = db_value

        return defaults

    async def initialize_defaults(self) -> None:
        """
        Initialize default configuration values.

        This should be called during application setup to ensure
        all required configuration keys exist.
        """
        defaults = [
            {
                "key": "model_temperature",
                "value": 0.3,
                "description": "LLM temperature (0-2, lower = more deterministic)",
            },
            {
                "key": "model_confidence_threshold",
                "value": 0.80,
                "description": "Minimum groundedness score for reliable responses",
            },
            {
                "key": "model_max_tool_calls",
                "value": 5,
                "description": "Maximum tool calls per agent turn",
            },
            {
                "key": "retrieval_top_k",
                "value": 5,
                "description": "Number of documents to retrieve",
            },
            {
                "key": "feature_google_drive_sync",
                "value": False,
                "description": "Enable Google Drive document sync",
            },
            {
                "key": "feature_sms_notifications",
                "value": False,
                "description": "Enable SMS notifications to farmers",
            },
        ]

        for config in defaults:
            existing = await self.get_config(config["key"])
            if existing is None:
                await self.set_config(
                    key=config["key"],
                    value=config["value"],
                    description=config["description"],
                )
