"""
Admin routes (protected).
"""

import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin, get_db_session
from src.api.services.job_queue import enqueue_job, get_job, update_job
from src.config.settings import get_settings
from src.database.models import (
    User,
    UserProfile,
    UserRole,
    SystemConfig,
    Document,
    DocumentChunk,
    Conversation,
    BackgroundJob,
    JobStatus,
    Message,
    ToolCall,
    EvaluationRun,
)

router = APIRouter()


@router.get("/config")
async def list_config(
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.key.asc()))
    items = result.scalars().all()
    return {
        "items": [
            {"key": item.key, "value": item.value, "description": item.description}
            for item in items
        ]
    }


class ConfigUpdate(BaseModel):
    value: dict
    description: Optional[str] = None


class ReembedRequest(BaseModel):
    document_id: Optional[str] = None
    limit: Optional[int] = None
    batch_size: int = 32


@router.get("/config/{key}")
async def get_config_value(
    key: str,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found")
    return {"key": item.key, "value": item.value, "description": item.description}


@router.put("/config/{key}")
async def set_config_value(
    key: str,
    payload: ConfigUpdate,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        item = SystemConfig(key=key, value=payload.value, description=payload.description)
        db.add(item)
    else:
        item.value = payload.value
        if payload.description is not None:
            item.description = payload.description

    await db.flush()
    return {"key": item.key, "value": item.value, "description": item.description}


@router.post("/embeddings/rebuild")
async def rebuild_embeddings(
    payload: ReembedRequest,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    job = await enqueue_job(
        db,
        kind="reembed",
        payload={
            "document_id": payload.document_id,
            "limit": payload.limit,
            "batch_size": payload.batch_size,
        },
    )
    return {"job_id": str(job.id), "status": job.status.value}


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status.value,
        "progress": job.progress,
        "total": job.total,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
        return {"status": job.status.value}

    await update_job(
        db,
        job.id,
        status=JobStatus.FAILED,
        error="Terminated by admin",
    )
    return {"status": "failed"}


@router.get("/jobs")
async def list_jobs(
    status_filter: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    stmt = select(BackgroundJob).order_by(BackgroundJob.created_at.desc())
    count_stmt = select(func.count(BackgroundJob.id))
    if status_filter:
        stmt = stmt.where(BackgroundJob.status == status_filter)
        count_stmt = count_stmt.where(BackgroundJob.status == status_filter)
    if kind:
        stmt = stmt.where(BackgroundJob.kind == kind)
        count_stmt = count_stmt.where(BackgroundJob.kind == kind)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()
    result = await db.execute(stmt.limit(limit).offset(offset))
    jobs = result.scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(job.id),
                "kind": job.kind,
                "status": job.status.value,
                "progress": job.progress,
                "total": job.total,
                "error": job.error,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
            for job in jobs
        ],
    }


class UserRoleUpdate(BaseModel):
    role: str
    email: Optional[str] = None


class UserCreate(BaseModel):
    email: str
    password: Optional[str] = None
    email_confirm: Optional[bool] = True


@router.post("/users/{user_id}/role")
async def set_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        role = UserRole(payload.role.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Use 'admin' or 'farmer'.",
        ) from exc

    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one_or_none()
    if db_user is None:
        db_user = User(id=user_id, email=payload.email, role=role)
        db.add(db_user)
        await db.flush()
    else:
        db_user.role = role
        if payload.email:
            db_user.email = payload.email

    await db.flush()
    return {"id": str(db_user.id), "role": db_user.role.value, "email": db_user.email}


@router.get("/users")
async def list_users(
    query: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    order_map = {
        "created_at": User.created_at,
        "role": User.role,
    }
    sort_column = order_map.get(sort_by, User.created_at)
    direction = sort_dir.lower()
    if direction not in {"asc", "desc"}:
        direction = "desc"
    order_clause = sort_column.asc() if direction == "asc" else sort_column.desc()

    base_query = (
        select(User, UserProfile)
        .join(UserProfile, UserProfile.user_id == User.id, isouter=True)
        .order_by(order_clause, User.created_at.desc())
    )
    count_query = select(func.count(User.id)).select_from(User)
    if query:
        pattern = f"%{query.lower()}%"
        clause = or_(
            func.lower(User.email).like(pattern),
            func.lower(UserProfile.name).like(pattern),
        )
        base_query = base_query.where(clause)
        count_query = count_query.join(
            UserProfile, UserProfile.user_id == User.id, isouter=True
        ).where(clause)

    base_query = base_query.limit(limit).offset(offset)
    result = await db.execute(base_query)
    items = result.all()
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(db_user.id),
                "email": db_user.email,
                "role": db_user.role.value,
                "created_at": db_user.created_at,
                "profile": {
                    "name": profile.name if profile else None,
                    "region": profile.region if profile else None,
                    "language": profile.language if profile else None,
                },
            }
            for db_user, profile in items
        ]
    }


@router.post("/users")
async def create_user(
    payload: UserCreate,
    user: dict = Depends(require_admin),
) -> dict:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase admin API is not configured",
        )

    url = f"{settings.supabase_url}/auth/v1/admin/users"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "Content-Type": "application/json",
    }
    body = {
        "email": payload.email,
        "email_confirm": payload.email_confirm,
    }
    if payload.password:
        body["password"] = payload.password

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=headers, json=body)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supabase admin create failed: {response.text}",
        )

    data = response.json()
    return {
        "id": data.get("id"),
        "email": data.get("email"),
        "created_at": data.get("created_at"),
    }


@router.get("/summary")
async def admin_summary(
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user_count = await db.execute(select(func.count(User.id)))
    doc_count = await db.execute(select(func.count(Document.id)))
    chunk_count = await db.execute(select(func.count(DocumentChunk.id)))
    convo_count = await db.execute(select(func.count(Conversation.id)))

    last_job_result = await db.execute(
        select(BackgroundJob).order_by(BackgroundJob.created_at.desc()).limit(1)
    )
    last_job = last_job_result.scalar_one_or_none()

    return {
        "users": user_count.scalar_one(),
        "documents": doc_count.scalar_one(),
        "chunks": chunk_count.scalar_one(),
        "conversations": convo_count.scalar_one(),
        "last_job": {
            "id": str(last_job.id),
            "kind": last_job.kind,
            "status": last_job.status.value,
            "created_at": last_job.created_at,
        }
        if last_job
        else None,
    }


@router.get("/memory/stats")
async def memory_stats(
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get memory usage statistics for monitoring."""
    from datetime import datetime, timedelta
    
    # Counts
    message_count = await db.execute(select(func.count(Message.id)))
    tool_call_count = await db.execute(select(func.count(ToolCall.id)))
    convo_count = await db.execute(select(func.count(Conversation.id)))
    
    # Old conversations (potential candidates for archiving)
    archive_threshold = datetime.utcnow() - timedelta(days=90)
    old_convo_count = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.created_at < archive_threshold)
    )
    
    # Long conversations (potential candidates for summarization)
    long_convo_result = await db.execute(
        select(Conversation.id, func.count(Message.id).label("msg_count"))
        .join(Message)
        .group_by(Conversation.id)
        .having(func.count(Message.id) > 50)
    )
    long_convo_count = len(list(long_convo_result.all()))
    
    # Average messages per conversation
    avg_messages_result = await db.execute(
        select(func.avg(func.count(Message.id)))
        .select_from(Conversation)
        .join(Message)
        .group_by(Conversation.id)
    )
    avg_messages = avg_messages_result.scalar_one_or_none() or 0.0
    
    return {
        "total_messages": message_count.scalar_one(),
        "total_tool_calls": tool_call_count.scalar_one(),
        "total_conversations": convo_count.scalar_one(),
        "old_conversations": old_convo_count.scalar_one(),  # >90 days
        "long_conversations": long_convo_count,  # >50 messages
        "avg_messages_per_conversation": round(float(avg_messages), 1),
        "archive_threshold_days": 90,
        "summarization_threshold_messages": 50,
    }


@router.post("/evaluation/run")
async def run_evaluation(
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Run the agent evaluation test suite and store results."""
    import asyncio
    import concurrent.futures
    from src.agent import create_agent
    from src.evaluation.test_suite import (
        run_test_suite,
        get_summary_stats,
    )
    
    # Create agent
    agent = create_agent()
    
    # Sample farmer context
    farmer_context = {
        "user_id": "admin_eval",
        "farms": [
            {
                "name": "Test Farm",
                "crops": [
                    {"type": "maize", "growth_stage": "vegetative"},
                    {"type": "beans", "growth_stage": "flowering"},
                ],
            }
        ],
    }
    
    # Run test suite (in thread to avoid blocking)
    def _run():
        results = run_test_suite(
            agent_run_fn=agent.run,
            farmer_context=farmer_context,
        )
        summary = get_summary_stats(results)
        return {
            "summary": summary,
            "results": [
                {
                    "test_id": r["test_case"].id,
                    "query": r["test_case"].query,
                    "category": r["test_case"].category,
                    "metrics": r["metrics"].to_dict() if r.get("metrics") else None,
                    "passed": r.get("passed", False),
                    "error": r.get("error"),
                }
                for r in results
            ],
        }
    
    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, _run)
    
    # Store evaluation run in database
    eval_run = EvaluationRun(
        run_by=uuid.UUID(user["user_id"]),
        summary=result["summary"],
        results=result["results"],
    )
    db.add(eval_run)
    await db.commit()
    
    # Add the run ID to the response
    result["run_id"] = str(eval_run.id)
    result["created_at"] = eval_run.created_at.isoformat()
    
    return result


@router.get("/evaluation/runs")
async def list_evaluation_runs(
    limit: int = 10,
    offset: int = 0,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """List past evaluation runs."""
    total_result = await db.execute(select(func.count(EvaluationRun.id)))
    total = total_result.scalar_one()
    
    runs_result = await db.execute(
        select(EvaluationRun)
        .order_by(EvaluationRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = runs_result.scalars().all()
    
    return {
        "items": [
            {
                "id": str(run.id),
                "run_by": str(run.run_by),
                "summary": run.summary,
                "created_at": run.created_at.isoformat(),
            }
            for run in runs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/evaluation/runs/{run_id}")
async def get_evaluation_run(
    run_id: str,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get a specific evaluation run with full results."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run ID")
    
    result = await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_uuid))
    run = result.scalar_one_or_none()
    
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found")
    
    return {
        "id": str(run.id),
        "run_by": str(run.run_by),
        "summary": run.summary,
        "results": run.results,
        "created_at": run.created_at.isoformat(),
    }
