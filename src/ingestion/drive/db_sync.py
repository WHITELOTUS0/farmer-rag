"""
Database-backed Google Drive sync for document ingestion.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from src.api.services.job_queue import update_job
from src.database.connection import AsyncSessionLocal
from src.database.models import Document, DocumentStatus, JobStatus
from src.ingestion.db_pipeline import DatabaseIngestionPipeline
from src.ingestion.drive.connector import GoogleDriveConnector

logger = logging.getLogger(__name__)


async def sync_drive_folder(
    job_id: str,
    folder_id: Optional[str] = None,
    force: bool = False,
) -> None:
    connector = GoogleDriveConnector()
    pipeline = DatabaseIngestionPipeline()

    async with AsyncSessionLocal() as session:
        await update_job(session, job_id, status=JobStatus.RUNNING, result={"message": "Starting Drive sync", "stage": "initializing"})

    # List files
    async with AsyncSessionLocal() as session:
        await update_job(session, job_id, result={"message": "Listing files in folder...", "stage": "listing"})
    
    files = await asyncio.to_thread(connector.list_files, folder_id)
    total = len(files)
    processed = 0

    async with AsyncSessionLocal() as session:
        await update_job(session, job_id, total=total, progress=0, result={"message": f"Found {total} files. Starting download...", "stage": "downloading"})

    for file in files:
        file_id = file["id"]
        file_name = file["name"]
        mime_type = file["mimeType"]
        modified_time = file.get("modifiedTime")

        async with AsyncSessionLocal() as session:
            existing = await session.execute(
                select(Document).where(Document.drive_file_id == file_id)
            )
            doc = existing.scalar_one_or_none()
            if doc and not force:
                prev_mod = None
                if doc.extra_metadata:
                    prev_mod = doc.extra_metadata.get("drive_modified_time")
                if prev_mod and modified_time and prev_mod >= modified_time:
                    processed += 1
                    await update_job(session, job_id, progress=processed)
                    continue

        # Download file
        async with AsyncSessionLocal() as session:
            await update_job(session, job_id, result={"message": f"Downloading: {file_name}", "stage": "downloading"})
        
        local_path = await asyncio.to_thread(
            connector.download_file,
            file_id=file_id,
            file_name=file_name,
            mime_type=mime_type,
        )
        if not local_path:
            processed += 1
            async with AsyncSessionLocal() as session:
                await update_job(session, job_id, progress=processed, result={"message": f"Skipped: {file_name} (download failed)", "stage": "processing"})
            continue

        # Ingest file
        async with AsyncSessionLocal() as session:
            await update_job(session, job_id, result={"message": f"Processing: {file_name}", "stage": "processing"})
            await pipeline.ingest_file(
                session,
                local_path,
                filename=file_name,
                source_url=f"https://drive.google.com/file/d/{file_id}/view",
                additional_metadata={
                    "drive_file_id": file_id,
                    "drive_modified_time": modified_time,
                },
            )
            await session.commit()

        processed += 1
        async with AsyncSessionLocal() as session:
            await update_job(session, job_id, progress=processed, result={"message": f"Completed: {file_name} ({processed}/{total})", "stage": "processing"})

    async with AsyncSessionLocal() as session:
        await update_job(session, job_id, status=JobStatus.COMPLETED, result={"message": "Drive sync complete"})
