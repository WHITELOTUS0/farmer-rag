"""
Knowledge base tool for RAG retrieval (LangChain @tool).
"""

import logging
from typing import Optional

from langchain_core.tools import tool

from src.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)

_retriever = Retriever()


@tool("query_agricultural_knowledge")
def query_agricultural_knowledge(
    query: str,
    crop_type: Optional[str] = None,
    topic: Optional[str] = None,
    top_k: int = 5,
) -> dict:
    """
    Search the agricultural knowledge base for relevant guidance.
    """
    try:
        if crop_type:
            crop_type = crop_type.lower().strip()
        if topic:
            topic = topic.lower().strip()

        results = _retriever.retrieve(
            query=query,
            crop_type=crop_type,
            topic=topic,
            top_k=top_k,
        )

        if not results:
            return {
                "query": query,
                "results": [],
                "message": "No relevant documents found in the knowledge base.",
            }

        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.append(
                {
                    "rank": i,
                    "text": result.text,
                    "source": result.source_name,
                    "source_id": result.source_id,
                    "confidence": round(result.similarity_score, 3),
                    "metadata": {
                        k: v
                        for k, v in result.metadata.items()
                        if k
                        in [
                            "crop_types",
                            "topics",
                            "growth_stages",
                            "has_numerical_data",
                        ]
                    },
                }
            )

        return {
            "query": query,
            "results": formatted_results,
            "context_for_response": _retriever.format_context_for_llm(results),
            "filters_applied": {"crop_type": crop_type, "topic": topic},
            "result_count": len(results),
        }
    except Exception as e:
        logger.error("Knowledge base query failed: %s", e)
        return {"error": f"Knowledge base query failed: {str(e)}"}
