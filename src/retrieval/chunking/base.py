"""
Base classes for document chunking.

Defines the interface for all chunking implementations
and common data structures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Chunk:
    """
    Represents a single chunk of text from a document.

    Attributes:
        text: The chunk text content
        chunk_index: Position of this chunk in the document
        metadata: Associated metadata (crop types, topics, etc.)
        source_id: ID of the source document
        source_name: Human-readable name of the source
    """
    text: str
    chunk_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    source_name: str = ""

    @property
    def id(self) -> str:
        """Generate a unique ID for this chunk."""
        return f"{self.source_id}_chunk_{self.chunk_index}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary for storage."""
        return {
            "text": self.text,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "id": self.id,
        }


@dataclass
class ChunkMetadata:
    """
    Metadata extracted from or about a chunk.

    Attributes:
        crop_types: List of crops mentioned (maize, beans, tomatoes)
        topics: List of topics covered (fertilizer, pest_control, etc.)
        growth_stages: Relevant growth stages mentioned
        has_numerical_data: Whether chunk contains measurements/dosages
        region_specific: Whether content is East Africa specific
        confidence: Confidence in metadata extraction
    """
    crop_types: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    growth_stages: List[str] = field(default_factory=list)
    has_numerical_data: bool = False
    region_specific: bool = False
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for storage."""
        return {
            "crop_types": ",".join(self.crop_types) if self.crop_types else "",
            "topics": ",".join(self.topics) if self.topics else "",
            "growth_stages": ",".join(self.growth_stages) if self.growth_stages else "",
            "has_numerical_data": self.has_numerical_data,
            "region_specific": self.region_specific,
            "metadata_confidence": self.confidence,
        }


class BaseChunker(ABC):
    """
    Abstract base class for document chunkers.

    All chunking implementations should inherit from this class
    and implement the chunk_text method.
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ):
        """
        Initialize the chunker.

        Args:
            chunk_size: Target size for chunks (in characters or tokens)
            chunk_overlap: Overlap between consecutive chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abstractmethod
    def chunk_text(
        self,
        text: str,
        source_id: str,
        source_name: str,
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """
        Split text into chunks.

        Args:
            text: The full document text
            source_id: Identifier for the source document
            source_name: Human-readable name of the source
            base_metadata: Metadata to include with all chunks

        Returns:
            List of Chunk objects
        """
        pass

    def _count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses a simple heuristic: ~4 characters per token for English.
        In production, use tiktoken for accurate counting.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4
