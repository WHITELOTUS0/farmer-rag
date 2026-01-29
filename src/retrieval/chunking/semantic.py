"""
Semantic chunking implementation for agricultural documents.

Splits documents at natural boundaries (paragraphs, sections) while
preserving context and ensuring chunks are appropriately sized.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from src.retrieval.chunking.base import BaseChunker, Chunk

logger = logging.getLogger(__name__)


class SemanticChunker(BaseChunker):
    """
    Semantic chunker that respects document structure.

    Features:
    - Splits at paragraph and section boundaries
    - Preserves context by including headers with content
    - Merges small paragraphs to reach target chunk size
    - Handles agricultural document structures (lists, tables as text)
    """

    # Patterns for detecting section boundaries
    SECTION_PATTERNS = [
        r'^#{1,6}\s+',  # Markdown headers
        r'^[A-Z][A-Z\s]{2,}:?\s*$',  # ALL CAPS HEADERS
        r'^\d+\.\s+[A-Z]',  # Numbered sections
        r'^(?:Chapter|Section|Part)\s+\d+',  # Formal sections
    ]

    # Patterns for paragraph boundaries
    PARAGRAPH_SEPARATORS = [
        r'\n\n+',  # Multiple newlines
        r'\n(?=\d+\.\s)',  # Before numbered lists
        r'\n(?=[-•]\s)',  # Before bullet points
    ]

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        min_chunk_size: int = 100,
    ):
        """
        Initialize the semantic chunker.

        Args:
            chunk_size: Target size for chunks (in characters)
            chunk_overlap: Overlap between consecutive chunks
            min_chunk_size: Minimum chunk size (smaller chunks get merged)
        """
        super().__init__(chunk_size, chunk_overlap)
        self.min_chunk_size = min_chunk_size

    def chunk_text(
        self,
        text: str,
        source_id: str,
        source_name: str,
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """
        Split text into semantically meaningful chunks.

        Args:
            text: The full document text
            source_id: Identifier for the source document
            source_name: Human-readable name of the source
            base_metadata: Metadata to include with all chunks

        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for source: {source_id}")
            return []

        # Clean the text
        text = self._clean_text(text)

        # Split into initial segments
        segments = self._split_into_segments(text)

        # Merge small segments and split large ones
        chunks = self._create_chunks(segments, source_id, source_name, base_metadata)

        logger.info(f"Created {len(chunks)} chunks from source: {source_name}")
        return chunks

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize text.

        Args:
            text: Raw document text

        Returns:
            Cleaned text
        """
        # Normalize whitespace
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\t', ' ', text)
        text = re.sub(r' +', ' ', text)

        # Remove excessive newlines (keep max 2)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove page numbers and headers/footers patterns
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)  # Standalone page numbers
        text = re.sub(r'Page \d+ of \d+', '', text)

        return text.strip()

    def _split_into_segments(self, text: str) -> List[Dict[str, Any]]:
        """
        Split text into initial segments at natural boundaries.

        Args:
            text: Cleaned document text

        Returns:
            List of segment dictionaries with text and type
        """
        segments = []

        # First, try to split by sections
        current_header = None
        current_content = []

        lines = text.split('\n')

        for line in lines:
            is_header = self._is_header(line)

            if is_header:
                # Save previous section if exists
                if current_content:
                    segment_text = '\n'.join(current_content).strip()
                    if segment_text:
                        segments.append({
                            "text": segment_text,
                            "header": current_header,
                            "type": "section",
                        })
                    current_content = []

                current_header = line.strip()
            else:
                current_content.append(line)

        # Don't forget the last section
        if current_content:
            segment_text = '\n'.join(current_content).strip()
            if segment_text:
                segments.append({
                    "text": segment_text,
                    "header": current_header,
                    "type": "section",
                })

        # If no sections found, split by paragraphs
        if not segments:
            paragraphs = re.split(r'\n\n+', text)
            for para in paragraphs:
                para = para.strip()
                if para:
                    segments.append({
                        "text": para,
                        "header": None,
                        "type": "paragraph",
                    })

        return segments

    def _is_header(self, line: str) -> bool:
        """
        Check if a line is a section header.

        Args:
            line: A single line of text

        Returns:
            True if line appears to be a header
        """
        line = line.strip()

        if not line:
            return False

        # Check against header patterns
        for pattern in self.SECTION_PATTERNS:
            if re.match(pattern, line):
                return True

        # Short lines in title case might be headers
        if len(line) < 100 and line.istitle() and not line.endswith('.'):
            return True

        return False

    def _create_chunks(
        self,
        segments: List[Dict[str, Any]],
        source_id: str,
        source_name: str,
        base_metadata: Optional[Dict[str, Any]],
    ) -> List[Chunk]:
        """
        Create appropriately-sized chunks from segments.

        Merges small segments and splits large ones.

        Args:
            segments: List of text segments
            source_id: Source document ID
            source_name: Source document name
            base_metadata: Base metadata for all chunks

        Returns:
            List of Chunk objects
        """
        chunks = []
        current_texts = []
        current_length = 0
        chunk_index = 0

        for segment in segments:
            segment_text = segment["text"]
            header = segment.get("header")

            # Prepend header to segment if available
            if header:
                segment_text = f"{header}\n\n{segment_text}"

            segment_length = len(segment_text)

            # If this segment alone is too large, split it
            if segment_length > self.chunk_size:
                # First, flush any accumulated text
                if current_texts:
                    chunk_text = '\n\n'.join(current_texts)
                    chunks.append(self._create_chunk(
                        text=chunk_text,
                        index=chunk_index,
                        source_id=source_id,
                        source_name=source_name,
                        base_metadata=base_metadata,
                    ))
                    chunk_index += 1
                    current_texts = []
                    current_length = 0

                # Split the large segment
                sub_chunks = self._split_large_segment(segment_text)
                for sub_text in sub_chunks:
                    chunks.append(self._create_chunk(
                        text=sub_text,
                        index=chunk_index,
                        source_id=source_id,
                        source_name=source_name,
                        base_metadata=base_metadata,
                    ))
                    chunk_index += 1
                continue

            # Check if adding this segment would exceed chunk size
            if current_length + segment_length > self.chunk_size and current_texts:
                # Create chunk from accumulated text
                chunk_text = '\n\n'.join(current_texts)
                chunks.append(self._create_chunk(
                    text=chunk_text,
                    index=chunk_index,
                    source_id=source_id,
                    source_name=source_name,
                    base_metadata=base_metadata,
                ))
                chunk_index += 1

                # Start new accumulation with overlap
                if self.chunk_overlap > 0 and current_texts:
                    # Keep last portion for overlap
                    overlap_text = current_texts[-1]
                    if len(overlap_text) > self.chunk_overlap:
                        overlap_text = overlap_text[-self.chunk_overlap:]
                    current_texts = [overlap_text]
                    current_length = len(overlap_text)
                else:
                    current_texts = []
                    current_length = 0

            # Add segment to accumulation
            current_texts.append(segment_text)
            current_length += segment_length

        # Flush remaining text
        if current_texts:
            chunk_text = '\n\n'.join(current_texts)
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(self._create_chunk(
                    text=chunk_text,
                    index=chunk_index,
                    source_id=source_id,
                    source_name=source_name,
                    base_metadata=base_metadata,
                ))
            elif chunks:
                # Merge with previous chunk if too small
                prev_chunk = chunks[-1]
                prev_chunk.text = f"{prev_chunk.text}\n\n{chunk_text}"

        return chunks

    def _split_large_segment(self, text: str) -> List[str]:
        """
        Split a large segment into smaller pieces.

        Tries to split at sentence boundaries.

        Args:
            text: Large text segment

        Returns:
            List of smaller text pieces
        """
        pieces = []

        # Split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)

        current_piece = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)

            if current_length + sentence_length > self.chunk_size and current_piece:
                pieces.append(' '.join(current_piece))
                current_piece = []
                current_length = 0

            current_piece.append(sentence)
            current_length += sentence_length

        if current_piece:
            pieces.append(' '.join(current_piece))

        return pieces

    def _create_chunk(
        self,
        text: str,
        index: int,
        source_id: str,
        source_name: str,
        base_metadata: Optional[Dict[str, Any]],
    ) -> Chunk:
        """
        Create a Chunk object with metadata.

        Args:
            text: Chunk text
            index: Chunk index in document
            source_id: Source document ID
            source_name: Source document name
            base_metadata: Base metadata to include

        Returns:
            Chunk object
        """
        metadata = base_metadata.copy() if base_metadata else {}
        metadata["source_id"] = source_id
        metadata["source_name"] = source_name
        metadata["chunk_index"] = index
        metadata["char_count"] = len(text)

        return Chunk(
            text=text,
            chunk_index=index,
            metadata=metadata,
            source_id=source_id,
            source_name=source_name,
        )
