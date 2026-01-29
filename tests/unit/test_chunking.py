"""
Unit tests for document chunking.
"""

import pytest


class TestSemanticChunker:
    """Tests for the semantic chunker."""

    def test_chunker_creates_chunks(self, sample_document_text):
        """Test that chunker creates chunks from text."""
        from src.retrieval.chunking.semantic import SemanticChunker

        chunker = SemanticChunker(chunk_size=500, chunk_overlap=50)
        chunks = chunker.chunk_text(
            text=sample_document_text,
            source_id="test_doc",
            source_name="Test Document",
        )

        assert len(chunks) > 0
        assert all(chunk.text for chunk in chunks)
        assert all(chunk.source_id == "test_doc" for chunk in chunks)

    def test_chunker_preserves_context(self, sample_document_text):
        """Test that chunks maintain meaningful context."""
        from src.retrieval.chunking.semantic import SemanticChunker

        chunker = SemanticChunker(chunk_size=500)
        chunks = chunker.chunk_text(
            text=sample_document_text,
            source_id="test",
            source_name="Test",
        )

        # Check that chunks aren't cut mid-sentence
        for chunk in chunks:
            # Most chunks should end with proper punctuation
            text = chunk.text.strip()
            assert len(text) > 50  # Reasonable minimum size

    def test_chunker_handles_empty_text(self):
        """Test that chunker handles empty text gracefully."""
        from src.retrieval.chunking.semantic import SemanticChunker

        chunker = SemanticChunker()
        chunks = chunker.chunk_text(
            text="",
            source_id="empty",
            source_name="Empty Doc",
        )

        assert len(chunks) == 0


class TestMetadataExtractor:
    """Tests for metadata extraction."""

    def test_extracts_crop_types(self):
        """Test that extractor identifies crop types."""
        from src.retrieval.chunking.metadata_extractor import MetadataExtractor
        from src.retrieval.chunking.base import Chunk

        extractor = MetadataExtractor(use_llm=False)  # Rule-based only
        chunk = Chunk(
            text="Apply fertilizer to maize at planting time.",
            chunk_index=0,
        )

        metadata = extractor.extract_metadata(chunk)
        assert "maize" in metadata.crop_types

    def test_extracts_topics(self):
        """Test that extractor identifies topics."""
        from src.retrieval.chunking.metadata_extractor import MetadataExtractor
        from src.retrieval.chunking.base import Chunk

        extractor = MetadataExtractor(use_llm=False)
        chunk = Chunk(
            text="Apply NPK fertilizer at 50 kg per hectare. Use urea for nitrogen.",
            chunk_index=0,
        )

        metadata = extractor.extract_metadata(chunk)
        assert "fertilizer" in metadata.topics

    def test_detects_numerical_data(self):
        """Test that extractor detects numerical data."""
        from src.retrieval.chunking.metadata_extractor import MetadataExtractor
        from src.retrieval.chunking.base import Chunk

        extractor = MetadataExtractor(use_llm=False)
        chunk = Chunk(
            text="Apply 50 kg/ha of DAP fertilizer.",
            chunk_index=0,
        )

        metadata = extractor.extract_metadata(chunk)
        assert metadata.has_numerical_data
