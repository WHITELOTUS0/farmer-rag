"""
High-level retriever for the RAG system.

Combines vector search with intelligent filtering and result formatting
for optimal use in the agricultural advisory agent.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.config.settings import get_settings
from src.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """
    Structured result from retrieval operations.

    Attributes:
        text: The retrieved text chunk
        source_id: ID of the source document
        source_name: Human-readable name of the source
        similarity_score: Cosine similarity score (0-1)
        metadata: Additional metadata about the chunk
    """
    text: str
    source_id: str
    source_name: str
    similarity_score: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "similarity_score": self.similarity_score,
            "metadata": self.metadata,
        }


class Retriever:
    """
    High-level retriever for agricultural knowledge base queries.

    Provides intelligent retrieval with:
    - Automatic query enhancement
    - Crop-specific filtering
    - Confidence-based filtering
    - Result deduplication
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        top_k: int | None = None,
        confidence_threshold: float | None = None,
    ):
        """
        Initialize the retriever.

        Args:
            vector_store: Vector store instance (creates new if not provided)
            top_k: Number of results to retrieve
            confidence_threshold: Minimum similarity score for results
        """
        settings = get_settings()
        self.vector_store = vector_store or VectorStore()
        self.top_k = top_k or settings.retrieval_top_k
        self.confidence_threshold = confidence_threshold or settings.confidence_threshold

    def retrieve(
        self,
        query: str,
        crop_type: Optional[str] = None,
        topic: Optional[str] = None,
        growth_stage: Optional[str] = None,
        top_k: Optional[int] = None,
        min_confidence: Optional[float] = None,
    ) -> List[RetrievalResult]:
        """
        Retrieve relevant documents for a query.

        Args:
            query: The search query
            crop_type: Optional filter by crop type
            topic: Optional filter by topic
            growth_stage: Optional filter by growth stage
            top_k: Override default top_k
            min_confidence: Override default confidence threshold

        Returns:
            List of RetrievalResult objects, sorted by relevance
        """
        effective_top_k = top_k or self.top_k
        effective_threshold = min_confidence or self.confidence_threshold

        # Build filters
        crop_types = [crop_type] if crop_type else None
        topics = [topic] if topic else None
        growth_stages = [growth_stage] if growth_stage else None

        # Execute search
        logger.debug(f"Retrieving for query: '{query[:50]}...' with filters: "
                    f"crop={crop_type}, topic={topic}, stage={growth_stage}")

        raw_results = self.vector_store.search_with_filter(
            query=query,
            crop_types=crop_types,
            topics=topics,
            growth_stages=growth_stages,
            top_k=effective_top_k * 2,  # Get extra for filtering
        )

        # Convert to RetrievalResult objects and filter by confidence
        results = []
        for raw in raw_results:
            if raw["similarity_score"] >= effective_threshold:
                result = RetrievalResult(
                    text=raw["text"],
                    source_id=raw["metadata"].get("source_id", "unknown"),
                    source_name=raw["metadata"].get("source_name", "Unknown Source"),
                    similarity_score=raw["similarity_score"],
                    metadata=raw["metadata"],
                )
                results.append(result)

        # Deduplicate by source (keep highest scoring chunk per source)
        deduplicated = self._deduplicate_by_source(results)

        # Return top_k results
        final_results = deduplicated[:effective_top_k]

        logger.info(f"Retrieved {len(final_results)} results for query "
                   f"(threshold={effective_threshold})")

        return final_results

    def retrieve_for_farmer_query(
        self,
        query: str,
        farmer_context: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        Retrieve documents with context-aware filtering.

        Uses farmer context (crops, growth stages) to improve retrieval relevance.

        Args:
            query: The farmer's question
            farmer_context: Dictionary with farmer's current state
            top_k: Number of results to retrieve

        Returns:
            List of relevant RetrievalResult objects
        """
        # Extract relevant filters from farmer context
        crop_types = []
        growth_stages = []

        if farmer_context:
            # Get all active crop types from farmer's farms
            for farm in farmer_context.get("farms", []):
                for crop in farm.get("crops", []):
                    if crop.get("type"):
                        crop_types.append(crop["type"])
                    if crop.get("growth_stage"):
                        growth_stages.append(crop["growth_stage"])

        # Deduplicate
        crop_types = list(set(crop_types))
        growth_stages = list(set(growth_stages))

        # Detect topic from query keywords
        topic = self._detect_topic(query)

        logger.debug(f"Context-aware retrieval: crops={crop_types}, "
                    f"stages={growth_stages}, topic={topic}")

        # First try with specific filters
        results = self.retrieve(
            query=query,
            crop_type=crop_types[0] if len(crop_types) == 1 else None,
            topic=topic,
            growth_stage=growth_stages[0] if len(growth_stages) == 1 else None,
            top_k=top_k,
        )

        # If not enough results, try without filters
        if len(results) < 3:
            logger.debug("Insufficient filtered results, expanding search...")
            results = self.retrieve(
                query=query,
                top_k=top_k,
            )

        return results

    def _deduplicate_by_source(
        self,
        results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """
        Keep only the highest-scoring chunk from each source document.

        This prevents the same document from dominating results.

        Args:
            results: List of retrieval results

        Returns:
            Deduplicated list of results
        """
        seen_sources = {}
        for result in results:
            source_id = result.source_id
            if source_id not in seen_sources:
                seen_sources[source_id] = result
            elif result.similarity_score > seen_sources[source_id].similarity_score:
                seen_sources[source_id] = result

        return sorted(
            seen_sources.values(),
            key=lambda x: x.similarity_score,
            reverse=True,
        )

    def _detect_topic(self, query: str) -> Optional[str]:
        """
        Detect the topic of a query based on keywords.

        Args:
            query: The search query

        Returns:
            Detected topic or None
        """
        query_lower = query.lower()

        topic_keywords = {
            "fertilizer": ["fertilizer", "fertiliser", "npk", "urea", "dap", "manure", "compost", "nutrient"],
            "pest_control": ["pest", "insect", "bug", "aphid", "worm", "beetle", "spray", "pesticide"],
            "disease": ["disease", "blight", "wilt", "rot", "fungus", "virus", "infection", "yellow"],
            "irrigation": ["water", "irrigation", "drought", "rain", "moisture", "dry"],
            "planting": ["plant", "seed", "sow", "spacing", "depth", "germination"],
            "harvesting": ["harvest", "mature", "ripe", "yield", "storage", "post-harvest"],
            "weeding": ["weed", "weeding", "herbicide", "grass"],
        }

        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return topic

        return None

    def format_context_for_llm(
        self,
        results: List[RetrievalResult],
        max_tokens: int = 3000,
    ) -> str:
        """
        Format retrieval results as context for the LLM.

        Creates a structured context string that includes source citations.

        Args:
            results: List of retrieval results
            max_tokens: Approximate token limit for context

        Returns:
            Formatted context string
        """
        if not results:
            return "No relevant documents found in the knowledge base."

        context_parts = []
        context_parts.append("=== RETRIEVED KNOWLEDGE BASE CONTEXT ===\n")

        for i, result in enumerate(results, 1):
            source_info = f"[Source {i}: {result.source_name}]"
            confidence_info = f"(Relevance: {result.similarity_score:.2f})"

            chunk_text = f"""
{source_info} {confidence_info}
{result.text}
---"""
            context_parts.append(chunk_text)

        context_parts.append("\n=== END OF RETRIEVED CONTEXT ===")

        full_context = "\n".join(context_parts)

        # Simple truncation if too long (in production, use tiktoken for accurate counting)
        if len(full_context) > max_tokens * 4:  # Rough estimate: 4 chars per token
            full_context = full_context[:max_tokens * 4] + "\n[Context truncated due to length]"

        return full_context
