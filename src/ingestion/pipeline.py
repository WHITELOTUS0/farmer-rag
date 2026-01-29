"""
Document ingestion pipeline.

Orchestrates the complete flow from document loading to vector storage:
1. Load documents from various sources
2. Chunk documents semantically
3. Extract metadata
4. Generate embeddings
5. Store in vector database
"""

import logging
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

from src.config.settings import get_settings
from src.ingestion.loaders.base import BaseLoader, LoadedDocument
from src.ingestion.loaders.pdf import PDFLoader
from src.ingestion.loaders.docx import DocxLoader
from src.retrieval.chunking.semantic import SemanticChunker
from src.retrieval.chunking.metadata_extractor import MetadataExtractor
from src.retrieval.chunking.base import Chunk
from src.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Complete document ingestion pipeline.

    Handles the full flow from raw documents to searchable vectors,
    with proper error handling and logging for each stage.
    """

    # Map file extensions to loaders
    LOADER_MAP = {
        ".pdf": PDFLoader,
        ".docx": DocxLoader,
    }

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        chunker: Optional[SemanticChunker] = None,
        metadata_extractor: Optional[MetadataExtractor] = None,
        use_llm_for_metadata: bool = True,
    ):
        """
        Initialize the ingestion pipeline.

        Args:
            vector_store: Vector store instance
            chunker: Document chunker instance
            metadata_extractor: Metadata extraction instance
            use_llm_for_metadata: Whether to use LLM for metadata extraction
        """
        settings = get_settings()

        self.vector_store = vector_store or VectorStore()
        self.chunker = chunker or SemanticChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        self.metadata_extractor = metadata_extractor or MetadataExtractor(
            use_llm=use_llm_for_metadata
        )

        # Initialize loaders
        self.loaders: Dict[str, BaseLoader] = {}
        for ext, loader_class in self.LOADER_MAP.items():
            self.loaders[ext] = loader_class()

    def ingest_file(
        self,
        file_path: str,
        source_url: Optional[str] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest a single file into the vector store.

        Args:
            file_path: Path to the document file
            source_url: Optional URL where document came from
            additional_metadata: Extra metadata to attach to all chunks

        Returns:
            Dictionary with ingestion results:
            - success: bool
            - document: LoadedDocument info
            - chunk_count: number of chunks created
            - error: error message if failed
        """
        path = Path(file_path)
        logger.info(f"Starting ingestion of: {path.name}")

        try:
            # Step 1: Load the document
            document = self._load_document(file_path)
            logger.info(f"Loaded document: {document.filename} "
                       f"({document.file_size} bytes, {len(document.content)} chars)")

            # Check if already ingested
            existing_chunks = self._check_existing(document.source_id)
            if existing_chunks > 0:
                logger.info(f"Document already ingested ({existing_chunks} chunks). "
                           "Deleting existing chunks for re-ingestion...")
                self.vector_store.delete_by_source(document.source_id)

            # Step 2: Chunk the document
            base_metadata = {
                "source_url": source_url or "",
                **(additional_metadata or {}),
            }
            chunks = self.chunker.chunk_text(
                text=document.content,
                source_id=document.source_id,
                source_name=document.filename,
                base_metadata=base_metadata,
            )
            logger.info(f"Created {len(chunks)} chunks")

            if not chunks:
                return {
                    "success": False,
                    "document": document.to_dict(),
                    "chunk_count": 0,
                    "error": "No chunks created - document may be empty",
                }

            # Step 3: Extract metadata for each chunk
            enriched_chunks = self.metadata_extractor.enrich_chunks(chunks)
            logger.info("Metadata extraction complete")

            # Step 4: Add to vector store
            self._add_chunks_to_vector_store(enriched_chunks)

            return {
                "success": True,
                "document": document.to_dict(),
                "chunk_count": len(chunks),
                "error": None,
            }

        except Exception as e:
            logger.error(f"Ingestion failed for {file_path}: {e}")
            return {
                "success": False,
                "document": {"filename": path.name, "file_path": str(path)},
                "chunk_count": 0,
                "error": str(e),
            }

    def ingest_directory(
        self,
        directory_path: str,
        recursive: bool = True,
    ) -> Dict[str, Any]:
        """
        Ingest all supported documents from a directory.

        Args:
            directory_path: Path to the directory
            recursive: Whether to search subdirectories

        Returns:
            Dictionary with overall results:
            - total_files: number of files found
            - successful: number successfully ingested
            - failed: number that failed
            - results: list of individual results
        """
        dir_path = Path(directory_path)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        logger.info(f"Ingesting documents from: {dir_path}")

        # Find all supported files
        pattern = "**/*" if recursive else "*"
        files = []
        for ext in self.LOADER_MAP.keys():
            files.extend(dir_path.glob(f"{pattern}{ext}"))

        logger.info(f"Found {len(files)} supported files")

        results = []
        successful = 0
        failed = 0

        for file_path in files:
            result = self.ingest_file(str(file_path))
            results.append(result)

            if result["success"]:
                successful += 1
            else:
                failed += 1

        return {
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

    def ingest_text(
        self,
        text: str,
        source_name: str,
        source_id: Optional[str] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest raw text content directly.

        Useful for programmatic ingestion without files.

        Args:
            text: The text content to ingest
            source_name: Name to identify this source
            source_id: Optional custom source ID
            additional_metadata: Extra metadata to attach

        Returns:
            Dictionary with ingestion results
        """
        source_id = source_id or f"text_{uuid.uuid4().hex[:12]}"
        logger.info(f"Ingesting text: {source_name}")

        try:
            # Check existing
            existing = self._check_existing(source_id)
            if existing > 0:
                self.vector_store.delete_by_source(source_id)

            # Chunk
            chunks = self.chunker.chunk_text(
                text=text,
                source_id=source_id,
                source_name=source_name,
                base_metadata=additional_metadata,
            )

            if not chunks:
                return {
                    "success": False,
                    "source_id": source_id,
                    "chunk_count": 0,
                    "error": "No chunks created",
                }

            # Enrich and store
            enriched_chunks = self.metadata_extractor.enrich_chunks(chunks)
            self._add_chunks_to_vector_store(enriched_chunks)

            return {
                "success": True,
                "source_id": source_id,
                "source_name": source_name,
                "chunk_count": len(chunks),
                "error": None,
            }

        except Exception as e:
            logger.error(f"Text ingestion failed: {e}")
            return {
                "success": False,
                "source_id": source_id,
                "chunk_count": 0,
                "error": str(e),
            }

    def _load_document(self, file_path: str) -> LoadedDocument:
        """
        Load a document using the appropriate loader.

        Args:
            file_path: Path to the document

        Returns:
            LoadedDocument instance

        Raises:
            ValueError: If file type is not supported
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext not in self.loaders:
            supported = ", ".join(self.loaders.keys())
            raise ValueError(
                f"Unsupported file type: {ext}. Supported: {supported}"
            )

        loader = self.loaders[ext]
        return loader.load(file_path)

    def _check_existing(self, source_id: str) -> int:
        """
        Check if a source has already been ingested.

        Args:
            source_id: Source document ID

        Returns:
            Number of existing chunks from this source
        """
        results = self.vector_store.collection.get(
            where={"source_id": source_id},
            include=[],
        )
        return len(results["ids"]) if results["ids"] else 0

    def _add_chunks_to_vector_store(self, chunks: List[Chunk]) -> None:
        """
        Add chunks to the vector store.

        Args:
            chunks: List of enriched chunks to add
        """
        texts = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        ids = [chunk.id for chunk in chunks]

        self.vector_store.add_documents(
            texts=texts,
            metadatas=metadatas,
            ids=ids,
        )

    def get_supported_extensions(self) -> List[str]:
        """Get list of supported file extensions."""
        return list(self.LOADER_MAP.keys())

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the ingested documents.

        Returns:
            Dictionary with vector store statistics
        """
        return self.vector_store.get_collection_stats()
