"""
Embedding service for generating text embeddings.

Uses OpenAI's text-embedding-3-small model for high-quality
embeddings suitable for agricultural document retrieval.
"""

import logging
from typing import List

from openai import OpenAI

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings using OpenAI.

    Provides a simple interface for embedding single texts or batches,
    with automatic batching for large document sets.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the embedding service.

        Args:
            model: Embedding model name (default: from settings)
            api_key: OpenAI API key (default: from settings)
        """
        settings = get_settings()
        self.model = model or settings.embedding_model
        self.client = OpenAI(api_key=api_key or settings.openai_api_key)
        self._embedding_dimension = None

    @property
    def embedding_dimension(self) -> int:
        """
        Get the embedding dimension for the current model.

        Returns:
            int: Dimension of embedding vectors
        """
        if self._embedding_dimension is None:
            # Get dimension by embedding a test string
            test_embedding = self.embed_text("test")
            self._embedding_dimension = len(test_embedding)
        return self._embedding_dimension

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        # Clean the text - OpenAI doesn't accept empty strings
        text = text.strip()
        if not text:
            text = " "  # Use space for empty text

        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding

    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Automatically batches requests to handle large document sets
        efficiently while respecting API limits.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call (max 2048 for OpenAI)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Clean texts
        cleaned_texts = [t.strip() if t.strip() else " " for t in texts]

        all_embeddings = []

        # Process in batches
        for i in range(0, len(cleaned_texts), batch_size):
            batch = cleaned_texts[i:i + batch_size]
            logger.debug(f"Embedding batch {i // batch_size + 1}, size: {len(batch)}")

            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )

            # Extract embeddings in order
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.

        This is an alias for embed_text, but named separately for
        clarity in retrieval contexts.

        Args:
            query: Search query text

        Returns:
            Embedding vector for the query
        """
        return self.embed_text(query)
