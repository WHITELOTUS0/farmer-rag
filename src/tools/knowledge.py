"""
Knowledge base tool for RAG retrieval.

Provides access to the agricultural knowledge base through
semantic search with metadata filtering.
"""

import logging
from typing import Optional, List

from pydantic import BaseModel, Field

from src.tools.base import BaseTool, ToolResult
from src.retrieval.retriever import Retriever
from src.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


class KnowledgeBaseArgs(BaseModel):
    """Arguments for the knowledge base tool."""
    query: str = Field(
        ...,
        description="The question or topic to search for in the agricultural knowledge base",
    )
    crop_type: Optional[str] = Field(
        default=None,
        description="Filter by crop type (maize, beans, or tomatoes)",
    )
    topic: Optional[str] = Field(
        default=None,
        description="Filter by topic (fertilizer, pest_control, disease, irrigation, planting, harvesting, weeding, soil)",
    )
    top_k: int = Field(
        default=5,
        description="Number of results to return (1-10)",
        ge=1,
        le=10,
    )


class KnowledgeBaseTool(BaseTool):
    """
    Agricultural knowledge base search tool.

    Provides semantic search over ingested agricultural documents
    with filtering capabilities for crop type, topic, and growth stage.

    This is the primary RAG tool for retrieving relevant information
    from extension manuals, FAO guides, and other agricultural resources.
    """

    name = "query_agricultural_knowledge"
    description = (
        "Search the agricultural knowledge base for information about farming practices, "
        "pest control, fertilizer application, disease management, planting, and harvesting. "
        "Use this tool when the farmer asks questions about how to do something, best practices, "
        "recommended dosages, or needs information from agricultural guides and manuals."
    )
    args_schema = KnowledgeBaseArgs

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        """
        Initialize the knowledge base tool.

        Args:
            retriever: Custom retriever instance
            vector_store: Custom vector store instance
        """
        super().__init__()

        if retriever:
            self.retriever = retriever
        elif vector_store:
            self.retriever = Retriever(vector_store=vector_store)
        else:
            # Create default retriever (will initialize vector store)
            self.retriever = Retriever()

    def _execute(
        self,
        query: str,
        crop_type: Optional[str] = None,
        topic: Optional[str] = None,
        top_k: int = 5,
    ) -> ToolResult:
        """
        Search the knowledge base.

        Args:
            query: Search query
            crop_type: Optional crop filter
            topic: Optional topic filter
            top_k: Number of results

        Returns:
            ToolResult with retrieved documents
        """
        try:
            logger.info(f"Knowledge base query: '{query[:50]}...'")

            # Normalize inputs
            if crop_type:
                crop_type = crop_type.lower().strip()
            if topic:
                topic = topic.lower().strip()

            # Execute retrieval
            results = self.retriever.retrieve(
                query=query,
                crop_type=crop_type,
                topic=topic,
                top_k=top_k,
            )

            if not results:
                return ToolResult(
                    success=True,
                    data={
                        "query": query,
                        "results": [],
                        "message": "No relevant documents found in the knowledge base.",
                    },
                    source="Agricultural Knowledge Base",
                    metadata={"result_count": 0},
                )

            # Format results for agent consumption
            formatted_results = []
            for i, result in enumerate(results, 1):
                formatted_results.append({
                    "rank": i,
                    "text": result.text,
                    "source": result.source_name,
                    "source_id": result.source_id,
                    "confidence": round(result.similarity_score, 3),
                    "metadata": {
                        k: v for k, v in result.metadata.items()
                        if k in ["crop_types", "topics", "growth_stages", "has_numerical_data"]
                    },
                })

            # Generate context string for LLM
            context_string = self.retriever.format_context_for_llm(results)

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": formatted_results,
                    "context_for_response": context_string,
                    "filters_applied": {
                        "crop_type": crop_type,
                        "topic": topic,
                    },
                },
                source="Agricultural Knowledge Base",
                metadata={
                    "result_count": len(results),
                    "avg_confidence": round(
                        sum(r.similarity_score for r in results) / len(results), 3
                    ),
                },
            )

        except Exception as e:
            logger.error(f"Knowledge base query failed: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Knowledge base query failed: {str(e)}",
                source="Agricultural Knowledge Base",
            )

    def get_collection_info(self) -> dict:
        """
        Get information about the knowledge base.

        Returns:
            Dictionary with collection statistics
        """
        return self.retriever.vector_store.get_collection_stats()
