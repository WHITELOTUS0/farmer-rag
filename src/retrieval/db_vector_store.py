"""
Vector search using pgvector via SQLAlchemy.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from src.database.connection import get_sync_session
from src.database.models import Document, DocumentChunk
from src.retrieval.embeddings import EmbeddingService


class DatabaseVectorStore:
    """pgvector-backed vector store for retrieval."""

    def __init__(self, embedding_service: EmbeddingService | None = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        query_embedding = self.embedding_service.embed_query(query)

        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(DocumentChunk, Document, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
            .order_by(distance.asc())
            .limit(top_k)
        )

        if filter_metadata:
            for key, value in filter_metadata.items():
                stmt = stmt.where(DocumentChunk.extra_metadata[key].as_string() == str(value))

        session = get_sync_session()
        try:
            rows = session.execute(stmt).all()
        finally:
            session.close()

        results: List[Dict[str, Any]] = []
        for chunk, doc, dist in rows:
            similarity = max(0.0, 1 - float(dist)) if dist is not None else 0.0
            metadata = dict(chunk.extra_metadata or {})
            metadata.setdefault("source_name", doc.filename)
            metadata.setdefault("source_id", str(doc.id))
            results.append(
                {
                    "text": chunk.content,
                    "metadata": metadata,
                    "similarity_score": similarity,
                    "id": str(chunk.id),
                }
            )

        return results

    def search_with_filter(
        self,
        query: str,
        crop_types: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        growth_stages: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        filters = {}
        if crop_types:
            filters["crop_types"] = crop_types[0]
        if topics:
            filters["topics"] = topics[0]
        if growth_stages:
            filters["growth_stages"] = growth_stages[0]

        return self.search(query, top_k=top_k, filter_metadata=filters if filters else None)
