"""
Background job worker loop.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.job_queue import claim_next_job, update_job
from src.database.connection import AsyncSessionLocal
from src.database.models import JobStatus
from src.ingestion.reembed import reembed_document_chunks
from src.ingestion.drive.db_sync import sync_drive_folder

logger = logging.getLogger(__name__)

REEMBED_TIMEOUT_SECONDS = 15 * 60
DRIVE_SYNC_TIMEOUT_SECONDS = 20 * 60


async def run_job(job, session: AsyncSession) -> None:
    try:
        if job.kind == "reembed":
            payload = job.payload or {}
            await asyncio.wait_for(
                reembed_document_chunks(
                    job.id,
                    document_id=payload.get("document_id"),
                    limit=payload.get("limit"),
                    batch_size=payload.get("batch_size", 32),
                ),
                timeout=REEMBED_TIMEOUT_SECONDS,
            )
            await update_job(
                session,
                job.id,
                status=JobStatus.COMPLETED,
                result={"message": "Re-embedding finished"},
            )
        elif job.kind == "drive_sync":
            payload = job.payload or {}
            await asyncio.wait_for(
                sync_drive_folder(
                    job.id,
                    folder_id=payload.get("folder_id"),
                    force=payload.get("force", False),
                ),
                timeout=DRIVE_SYNC_TIMEOUT_SECONDS,
            )
            await update_job(
                session,
                job.id,
                status=JobStatus.COMPLETED,
                result={"message": "Drive sync finished"},
            )
        else:
            await update_job(
                session,
                job.id,
                status=JobStatus.FAILED,
                error=f"Unknown job kind: {job.kind}",
            )
    except asyncio.TimeoutError:
        logger.warning("Job %s (%s) timed out", job.id, job.kind)
        await update_job(
            session,
            job.id,
            status=JobStatus.FAILED,
            error="Job timed out",
        )
    except Exception as exc:
        await update_job(
            session,
            job.id,
            status=JobStatus.FAILED,
            error=str(exc),
        )


async def worker_loop(poll_interval: int = 5) -> None:
    logger.info("Job worker started (poll_interval=%ss)", poll_interval)
    while True:
        async with AsyncSessionLocal() as session:
            job = await claim_next_job(session)
            if job:
                await session.commit()
                await run_job(job, session)
                await session.commit()
            else:
                await session.rollback()
        await asyncio.sleep(poll_interval)
