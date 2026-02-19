"""
Vector search endpoint.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session
from src.database.models import Document, DocumentChunk
from src.retrieval.embeddings import EmbeddingService

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    source_id: Optional[str] = None


@router.post("/")
async def search(
    payload: SearchRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    embedding_service = EmbeddingService()
    query_embedding = embedding_service.embed_query(payload.query)

    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    stmt = (
        select(DocumentChunk, Document, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .order_by(distance.asc())
        .limit(payload.top_k)
    )
    if payload.source_id:
        stmt = stmt.where(DocumentChunk.extra_metadata["source_id"].as_string() == payload.source_id)

    rows = (await db.execute(stmt)).all()

    results = []
    for chunk, doc, dist in rows:
        similarity = max(0.0, 1 - float(dist)) if dist is not None else 0.0
        results.append(
            {
                "id": str(chunk.id),
                "text": chunk.content,
                "similarity_score": similarity,
                "source_id": str(doc.id),
                "source_name": doc.filename,
                "metadata": chunk.extra_metadata or {},
            }
        )

    return {"query": payload.query, "results": results, "count": len(results)}
