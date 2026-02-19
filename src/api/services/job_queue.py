"""
Database-backed job queue helpers.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import BackgroundJob, JobStatus


async def enqueue_job(
    db: AsyncSession,
    kind: str,
    payload: Optional[dict] = None,
    run_after: Optional[datetime] = None,
) -> BackgroundJob:
    job = BackgroundJob(
        kind=kind,
        payload=payload,
        run_after=run_after,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.flush()
    return job


async def get_job(db: AsyncSession, job_id: str) -> Optional[BackgroundJob]:
    result = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
    return result.scalar_one_or_none()


async def claim_next_job(db: AsyncSession) -> Optional[BackgroundJob]:
    now = datetime.utcnow()
    stmt = (
        select(BackgroundJob)
        .where(
            BackgroundJob.status == JobStatus.QUEUED,
            (BackgroundJob.run_after.is_(None) | (BackgroundJob.run_after <= now)),
        )
        .order_by(BackgroundJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        return None

    job.status = JobStatus.RUNNING
    await db.flush()
    return job


async def update_job(
    db: AsyncSession,
    job_id: str,
    **updates: dict,
) -> None:
    await db.execute(
        update(BackgroundJob)
        .where(BackgroundJob.id == job_id)
        .values(**updates, updated_at=datetime.utcnow())
    )
