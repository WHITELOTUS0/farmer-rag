"""
Google Drive sync service for automatic document ingestion.

Monitors a Google Drive folder and automatically ingests
new or updated documents into the knowledge base.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.config.settings import get_settings
from src.ingestion.drive.connector import GoogleDriveConnector
from src.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


class DriveSync:
    """
    Synchronization service for Google Drive documents.

    Provides methods for:
    - Manual sync: Pull all documents from Drive folder
    - Incremental sync: Pull only new/modified documents
    - Status tracking: Know which documents are synced
    """

    def __init__(
        self,
        connector: Optional[GoogleDriveConnector] = None,
        pipeline: Optional[IngestionPipeline] = None,
    ):
        """
        Initialize the sync service.

        Args:
            connector: Google Drive connector instance
            pipeline: Ingestion pipeline instance
        """
        self.connector = connector or GoogleDriveConnector()
        self.pipeline = pipeline or IngestionPipeline()
        self.settings = get_settings()

        # Track synced files (in production, store in database)
        self._synced_files: Dict[str, datetime] = {}

    def sync_folder(
        self,
        folder_id: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Sync all documents from a Google Drive folder.

        Args:
            folder_id: Google Drive folder ID (uses config default if None)
            force: Re-sync even if file hasn't changed

        Returns:
            Dictionary with sync results
        """
        folder_id = folder_id or self.settings.google_drive_folder_id

        if not folder_id:
            return {
                "success": False,
                "error": "No folder ID configured. Set GOOGLE_DRIVE_FOLDER_ID in .env",
                "files_processed": 0,
            }

        logger.info(f"Starting sync from folder: {folder_id}")

        # Authenticate
        if not self.connector.authenticate():
            return {
                "success": False,
                "error": "Google Drive authentication failed",
                "files_processed": 0,
            }

        # List files
        files = self.connector.list_files(folder_id)

        if not files:
            return {
                "success": True,
                "message": "No supported files found in folder",
                "files_processed": 0,
            }

        # Process each file
        results = {
            "success": True,
            "total_files": len(files),
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "details": [],
        }

        for file in files:
            file_id = file["id"]
            file_name = file["name"]
            mime_type = file["mimeType"]
            modified_time = file.get("modifiedTime", "")

            # Check if already synced (unless force)
            if not force and self._is_synced(file_id, modified_time):
                logger.debug(f"Skipping unchanged file: {file_name}")
                results["skipped"] += 1
                continue

            # Download file
            logger.info(f"Downloading: {file_name}")
            local_path = self.connector.download_file(
                file_id=file_id,
                file_name=file_name,
                mime_type=mime_type,
            )

            if not local_path:
                results["failed"] += 1
                results["details"].append({
                    "file": file_name,
                    "status": "download_failed",
                })
                continue

            # Ingest into knowledge base
            logger.info(f"Ingesting: {file_name}")
            ingest_result = self.pipeline.ingest_file(
                file_path=local_path,
                source_url=f"https://drive.google.com/file/d/{file_id}/view",
                additional_metadata={
                    "drive_file_id": file_id,
                    "drive_modified_time": modified_time,
                },
            )

            if ingest_result["success"]:
                results["processed"] += 1
                results["details"].append({
                    "file": file_name,
                    "status": "success",
                    "chunks": ingest_result["chunk_count"],
                })
                # Mark as synced
                self._mark_synced(file_id, modified_time)
            else:
                results["failed"] += 1
                results["details"].append({
                    "file": file_name,
                    "status": "ingest_failed",
                    "error": ingest_result["error"],
                })

        logger.info(
            f"Sync complete: {results['processed']} processed, "
            f"{results['skipped']} skipped, {results['failed']} failed"
        )

        return results

    def get_sync_status(self, folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current sync status for a folder.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            Dictionary with sync status
        """
        folder_id = folder_id or self.settings.google_drive_folder_id

        if not folder_id:
            return {"configured": False}

        # Try to authenticate and list files
        if not self.connector.authenticate():
            return {
                "configured": True,
                "authenticated": False,
                "error": "Authentication required",
            }

        files = self.connector.list_files(folder_id)

        # Count synced vs unsynced
        synced = 0
        unsynced = 0

        for file in files:
            if file["id"] in self._synced_files:
                synced += 1
            else:
                unsynced += 1

        return {
            "configured": True,
            "authenticated": True,
            "folder_id": folder_id,
            "total_files": len(files),
            "synced_files": synced,
            "pending_files": unsynced,
        }

    def _is_synced(self, file_id: str, modified_time: str) -> bool:
        """
        Check if a file is already synced with latest version.

        Args:
            file_id: Google Drive file ID
            modified_time: File modification timestamp

        Returns:
            True if synced and up to date
        """
        if file_id not in self._synced_files:
            return False

        # Parse and compare timestamps
        try:
            synced_time = self._synced_files[file_id]
            file_modified = datetime.fromisoformat(
                modified_time.replace("Z", "+00:00")
            )
            return synced_time >= file_modified
        except Exception:
            return False

    def _mark_synced(self, file_id: str, modified_time: str) -> None:
        """
        Mark a file as synced.

        Args:
            file_id: Google Drive file ID
            modified_time: File modification timestamp
        """
        try:
            self._synced_files[file_id] = datetime.fromisoformat(
                modified_time.replace("Z", "+00:00")
            )
        except Exception:
            self._synced_files[file_id] = datetime.now()


def sync_from_drive(folder_id: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """
    Convenience function to sync documents from Google Drive.

    Args:
        folder_id: Google Drive folder ID
        force: Force re-sync of all documents

    Returns:
        Sync results dictionary
    """
    sync = DriveSync()
    return sync.sync_folder(folder_id, force)
