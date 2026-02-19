"""
Background job helpers for re-embedding document chunks.
"""

import asyncio
from typing import Optional

from sqlalchemy import select, func

from src.api.services.job_queue import update_job
from src.database.connection import AsyncSessionLocal
from src.database.models import DocumentChunk, JobStatus
from src.retrieval.embeddings import EmbeddingService


async def reembed_document_chunks(
    job_id: str,
    document_id: Optional[str] = None,
    limit: Optional[int] = None,
    batch_size: int = 32,
) -> None:
    embedding_service = EmbeddingService()

    async with AsyncSessionLocal() as session:
        await update_job(session, job_id, status=JobStatus.RUNNING, result={"message": "Starting re-embedding"})
        count_stmt = select(func.count(DocumentChunk.id))
        if document_id:
            count_stmt = count_stmt.where(DocumentChunk.document_id == document_id)
        total = (await session.execute(count_stmt)).scalar_one()
        if limit is not None:
            total = min(total, limit)

        await update_job(session, job_id, total=total, progress=0)

        offset = 0
        processed = 0
        while processed < total:
            stmt = (
                select(DocumentChunk)
                .order_by(DocumentChunk.created_at.asc())
                .limit(batch_size)
                .offset(offset)
            )
            if document_id:
                stmt = stmt.where(DocumentChunk.document_id == document_id)

            result = await session.execute(stmt)
            chunks = result.scalars().all()
            if not chunks:
                break

            texts = [chunk.content for chunk in chunks]
            embeddings = await asyncio.to_thread(embedding_service.embed_documents, texts)
            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = emb

            await session.commit()

            processed += len(chunks)
            offset += len(chunks)
            await update_job(session, job_id, progress=min(processed, total))

        await update_job(session, job_id, status=JobStatus.COMPLETED, result={"message": "Re-embedding finished"})
