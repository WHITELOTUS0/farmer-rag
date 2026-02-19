"""
Health check endpoints.
"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session

router = APIRouter()


@router.get("/")
def health() -> dict:
    return {"status": "ok"}


@router.get("/db")
async def health_db(db: AsyncSession = Depends(get_db_session)) -> dict:
    start = time.perf_counter()
    await db.execute(text("SELECT 1"))
    latency_ms = int((time.perf_counter() - start) * 1000)
    return {"status": "ok", "db": "ok", "latency_ms": latency_ms}
