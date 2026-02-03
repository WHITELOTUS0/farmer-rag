"""
Vector store implementation using LangChain's Chroma wrapper.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config.settings import get_settings
from src.retrieval.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStore:
    """Chroma vector store wrapper with metadata filtering."""

    def __init__(
        self,
        collection_name: str | None = None,
        persist_directory: str | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        settings = get_settings()
        self.collection_name = collection_name or settings.chroma_collection_name
        self.persist_directory = persist_directory or settings.chroma_persist_directory
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        self.embedding_service = embedding_service or EmbeddingService()

        self.store = Chroma(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_service.embeddings,
        )

        logger.info(
            "Initialized vector store: collection='%s', persist_directory='%s'",
            self.collection_name,
            self.persist_directory,
        )

    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        if not texts:
            logger.warning("No texts provided to add_documents")
            return

        documents = [
            Document(page_content=text, metadata=metadata)
            for text, metadata in zip(texts, metadatas)
        ]
        self.store.add_documents(documents=documents, ids=ids)
        if hasattr(self.store, "persist"):
            self.store.persist()
        logger.info("Added %s documents to vector store", len(texts))

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        where = self._build_where_clause(filter_metadata) if filter_metadata else None

        formatted_results: List[Dict[str, Any]] = []
        try:
            results = self.store.similarity_search_with_relevance_scores(
                query=query,
                k=top_k,
                filter=where,
            )
            for doc, score in results:
                formatted_results.append(
                    {
                        "text": doc.page_content,
                        "metadata": doc.metadata or {},
                        "similarity_score": score,
                        "id": doc.metadata.get("id"),
                    }
                )
        except Exception:
            results = self.store.similarity_search_with_score(
                query=query,
                k=top_k,
                filter=where,
            )
            for doc, score in results:
                similarity = 1 / (1 + score) if score > 1 else 1 - score
                formatted_results.append(
                    {
                        "text": doc.page_content,
                        "metadata": doc.metadata or {},
                        "similarity_score": similarity,
                        "id": doc.metadata.get("id"),
                    }
                )

        if not formatted_results:
            results = self.store.similarity_search(
                query=query,
                k=top_k,
                filter=where,
            )
            for doc in results:
                formatted_results.append(
                    {
                        "text": doc.page_content,
                        "metadata": doc.metadata or {},
                        "similarity_score": 0.0,
                        "id": doc.metadata.get("id"),
                    }
                )

        return formatted_results

    def search_with_filter(
        self,
        query: str,
        crop_types: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        growth_stages: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search with agricultural-specific filters.

        This is a convenience method for common filtering patterns
        in the farmer advisory system.

        Args:
            query: Search query text
            crop_types: Filter by crop types (maize, beans, tomatoes)
            topics: Filter by topics (fertilizer, pest_control, irrigation)
            growth_stages: Filter by growth stages
            top_k: Number of results to return

        Returns:
            List of filtered search results
        """
        filters = {}

        # Build filter for crop types
        if crop_types:
            filters["crop_types"] = {"$eq": crop_types[0]}

        # Build filter for topics
        if topics:
            filters["topics"] = {"$eq": topics[0]}

        # Build filter for growth stages
        if growth_stages:
            filters["growth_stages"] = {"$eq": growth_stages[0]}

        return self.search(query, top_k=top_k, filter_metadata=filters if filters else None)

    def _build_where_clause(
        self,
        filters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build ChromaDB where clause from filters.

        Args:
            filters: Dictionary of field -> value or field -> operator dict

        Returns:
            ChromaDB-compatible where clause
        """
        if not filters:
            return None

        conditions = []
        for field, value in filters.items():
            if isinstance(value, dict):
                # Already in operator format
                conditions.append({field: value})
            else:
                # Simple equality
                conditions.append({field: {"$eq": value}})

        if len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}

    def delete_by_source(self, source_id: str) -> int:
        """
        Delete all documents from a specific source.

        Useful when re-ingesting a document.

        Args:
            source_id: Source document ID

        Returns:
            Number of documents deleted
        """
        # Get IDs of documents with this source
        results = self.store.get(where={"source_id": source_id}, include=[])
        ids = results.get("ids") if results else None
        if ids:
            self.store.delete(ids=ids)
            logger.info("Deleted %s chunks from source: %s", len(ids), source_id)
            return len(ids)
        return 0

    def delete_by_ids(self, ids: List[str]) -> None:
        """
        Delete documents by their IDs.

        Args:
            ids: List of document IDs to delete
        """
        if ids:
            self.store.delete(ids=ids)
            logger.info("Deleted %s documents from vector store", len(ids))

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store collection.

        Returns:
            Dictionary with collection statistics
        """
        count = self.store._collection.count()
        sample = self.store._collection.peek(limit=min(100, count))
        sources = set()
        crop_types = set()
        if sample.get("metadatas"):
            for metadata in sample["metadatas"]:
                if "source_id" in metadata:
                    sources.add(metadata["source_id"])
                if "crop_types" in metadata:
                    for ct in str(metadata["crop_types"]).split(","):
                        if ct:
                            crop_types.add(ct.strip())
        return {
            "total_documents": count,
            "collection_name": self.collection_name,
            "unique_sources_sample": len(sources),
            "crop_types_sample": list(crop_types),
        }

    def reset(self) -> None:
        """
        Reset the collection by deleting all documents.

        WARNING: This will delete all data in the collection.
        """
        self.store.delete_collection()
        self.store = Chroma(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_service.embeddings,
        )
        logger.warning("Reset collection: %s", self.collection_name)
