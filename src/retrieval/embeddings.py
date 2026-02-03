"""
Embedding service backed by LangChain's OpenAIEmbeddings.
"""

from typing import List

from langchain_openai import OpenAIEmbeddings

from src.config.settings import get_settings


class EmbeddingService:
    """Wrapper around LangChain embeddings for consistent usage."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self.embeddings = OpenAIEmbeddings(
            model=model or settings.embedding_model,
            api_key=api_key or settings.openai_api_key,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embeddings.embed_documents(texts)

    def embed_query(self, query: str) -> List[float]:
        return self.embeddings.embed_query(query)
