"""
Vector store implementation using ChromaDB.

Provides persistent storage for document embeddings with
metadata filtering capabilities for agricultural content.
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config.settings import get_settings
from src.retrieval.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB-based vector store for agricultural document retrieval.

    Supports:
    - Persistent storage for production use
    - Metadata filtering by crop type, topic, growth stage
    - Efficient similarity search with configurable top-k
    """

    def __init__(
        self,
        collection_name: str | None = None,
        persist_directory: str | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        """
        Initialize the vector store.

        Args:
            collection_name: Name of the ChromaDB collection
            persist_directory: Directory for persistent storage
            embedding_service: Service for generating embeddings
        """
        settings = get_settings()
        self.collection_name = collection_name or settings.chroma_collection_name
        self.persist_directory = persist_directory or settings.chroma_persist_directory

        # Ensure persist directory exists
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService()

        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},  # Use cosine similarity
        )

        logger.info(
            f"Initialized vector store: collection='{self.collection_name}', "
            f"persist_directory='{self.persist_directory}', "
            f"document_count={self.collection.count()}"
        )

    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        """
        Add documents to the vector store.

        Args:
            texts: List of document texts (chunks)
            metadatas: List of metadata dicts for each document
            ids: List of unique IDs for each document
        """
        if not texts:
            logger.warning("No texts provided to add_documents")
            return

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(texts)} documents...")
        embeddings = self.embedding_service.embed_texts(texts)

        # Clean metadata - ChromaDB only accepts str, int, float, bool
        cleaned_metadatas = []
        for metadata in metadatas:
            cleaned = {}
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    cleaned[key] = value
                elif isinstance(value, list):
                    # Convert lists to comma-separated strings
                    cleaned[key] = ",".join(str(v) for v in value)
                elif value is None:
                    cleaned[key] = ""
                else:
                    cleaned[key] = str(value)
            cleaned_metadatas.append(cleaned)

        # Add to collection
        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=cleaned_metadatas,
            ids=ids,
        )

        logger.info(f"Added {len(texts)} documents to vector store")

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.

        Args:
            query: Search query text
            top_k: Number of results to return
            filter_metadata: Optional metadata filters

        Returns:
            List of results with text, metadata, and similarity score
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_query(query)

        # Build where clause for filtering
        where = None
        if filter_metadata:
            where = self._build_where_clause(filter_metadata)

        # Execute search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # Format results
        formatted_results = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                # Convert distance to similarity score (cosine distance to similarity)
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 - distance  # Cosine similarity = 1 - cosine distance

                formatted_results.append({
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "similarity_score": similarity,
                    "id": results["ids"][0][i] if results["ids"] else None,
                })

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
            # ChromaDB uses $contains for string matching
            # Since we store crop_types as comma-separated string
            filters["crop_types"] = {"$contains": crop_types[0]}

        # Build filter for topics
        if topics:
            filters["topics"] = {"$contains": topics[0]}

        # Build filter for growth stages
        if growth_stages:
            filters["growth_stages"] = {"$contains": growth_stages[0]}

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
        results = self.collection.get(
            where={"source_id": source_id},
            include=[],
        )

        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(f"Deleted {len(results['ids'])} chunks from source: {source_id}")
            return len(results["ids"])

        return 0

    def delete_by_ids(self, ids: List[str]) -> None:
        """
        Delete documents by their IDs.

        Args:
            ids: List of document IDs to delete
        """
        if ids:
            self.collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} documents from vector store")

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store collection.

        Returns:
            Dictionary with collection statistics
        """
        count = self.collection.count()

        # Sample some documents to get metadata distribution
        sample = self.collection.peek(limit=min(100, count))

        # Count unique sources
        sources = set()
        crop_types = set()
        if sample["metadatas"]:
            for metadata in sample["metadatas"]:
                if "source_id" in metadata:
                    sources.add(metadata["source_id"])
                if "crop_types" in metadata:
                    for ct in metadata["crop_types"].split(","):
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
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning(f"Reset collection: {self.collection_name}")
