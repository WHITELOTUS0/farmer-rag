"""
Document ingestion endpoints.
"""

import json
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.api.deps import require_admin, get_db_session
from src.api.services.job_queue import enqueue_job
from src.ingestion.db_pipeline import DatabaseIngestionPipeline
from src.ingestion.drive.connector import GoogleDriveConnector
from src.config.settings import get_settings
from src.database.models import Document

router = APIRouter()


class DriveSyncRequest(BaseModel):
    folder_id: Optional[str] = None
    force: bool = False


@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    source_url: Optional[str] = Form(default=None),
    metadata: Optional[str] = Form(default=None),
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    meta = {}
    if metadata:
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid metadata JSON",
            ) from exc

    suffix = os.path.splitext(file.filename or "")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        pipeline = DatabaseIngestionPipeline()
        result = await pipeline.ingest_file(
            db,
            tmp_path,
            filename=file.filename,
            source_url=source_url,
            additional_metadata=meta,
        )
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("/drive-sync")
async def drive_sync(
    payload: DriveSyncRequest,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    job = await enqueue_job(
        db,
        kind="drive_sync",
        payload={"folder_id": payload.folder_id, "force": payload.force},
    )
    return {"job_id": str(job.id), "status": job.status.value}


@router.get("/oauth/authorize")
async def get_google_oauth_url(
    redirect_uri: Optional[str] = Query(None, description="Frontend callback URL"),
    user: dict = Depends(require_admin),
) -> dict:
    """
    Generate Google OAuth authorization URL for web-based authentication.
    """
    settings = get_settings()
    connector = GoogleDriveConnector()

    # Use provided redirect_uri or fall back to settings
    final_redirect_uri = redirect_uri or settings.google_oauth_redirect_uri
    if not final_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri must be provided as query parameter or set GOOGLE_OAUTH_REDIRECT_URI in settings",
        )

    auth_url, code_verifier = connector.get_authorization_url(final_redirect_uri)
    if not auth_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL. Check credentials file.",
        )

    return {"authorization_url": auth_url, "code_verifier": code_verifier}


@router.post("/oauth/callback")
async def handle_google_oauth_callback(
    code: str = Form(...),
    redirect_uri: str = Form(...),
    code_verifier: Optional[str] = Form(default=None),
    user: dict = Depends(require_admin),
) -> dict:
    """
    Exchange OAuth authorization code for access token.
    code_verifier must be the value returned by /oauth/authorize (PKCE).
    """
    connector = GoogleDriveConnector()
    success, error_msg = connector.exchange_code_for_token(code, redirect_uri, code_verifier)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "Failed to exchange authorization code for token",
        )

    return {"success": True, "message": "Google Drive authentication successful"}


@router.get("/")
async def list_documents(
    query: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    stmt = select(Document).order_by(Document.created_at.desc())
    count_stmt = select(func.count(Document.id))
    if query:
        stmt = stmt.where(func.lower(Document.filename).like(f"%{query.lower()}%"))
        count_stmt = count_stmt.where(
            func.lower(Document.filename).like(f"%{query.lower()}%")
        )
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
        count_stmt = count_stmt.where(Document.status == status_filter)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    result = await db.execute(stmt.limit(limit).offset(offset))
    docs = result.scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "status": doc.status.value,
                "source_type": doc.source_type,
                "source_url": doc.source_url,
                "chunk_count": doc.chunk_count,
                "error_message": doc.error_message,
                "created_at": doc.created_at,
                "processed_at": doc.processed_at,
            }
            for doc in docs
        ],
    }
