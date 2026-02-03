"""
Document ingestion pipeline using LangChain loaders and splitters.
"""

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredFileLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker

from src.config.settings import get_settings
from src.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """End-to-end ingestion using LangChain primitives."""

    LOADER_MAP = {
        ".pdf": [PyPDFLoader],
        ".docx": [Docx2txtLoader, UnstructuredFileLoader],
        ".txt": [TextLoader],
    }

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        splitter: Optional[object] = None,
    ):
        settings = get_settings()
        self.vector_store = vector_store or VectorStore()
        if splitter is not None:
            self.splitter = splitter
        else:
            # Semantic chunking (preferred for HW2 advanced chunking)
            self.splitter = SemanticChunker(
                self.vector_store.embedding_service.embeddings,
                breakpoint_threshold_type="percentile",
                breakpoint_threshold_amount=0.8,
            )

    def ingest_file(
        self,
        file_path: str,
        source_url: Optional[str] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        path = Path(file_path)
        logger.info("Starting ingestion of: %s", path.name)

        try:
            documents = self._load_documents(file_path)
            if not documents:
                return {
                    "success": False,
                    "document": {"filename": path.name, "file_path": str(path)},
                    "chunk_count": 0,
                    "error": "No documents loaded - file may be empty",
                }

            source_id = self._build_source_id(path)
            for doc in documents:
                doc.metadata.update(
                    {
                        "source_id": source_id,
                        "source_name": path.name,
                        "source_url": source_url or "",
                        **(additional_metadata or {}),
                    }
                )

            if self._check_existing(source_id) > 0:
                logger.info("Re-ingesting %s; clearing prior chunks", source_id)
                self.vector_store.delete_by_source(source_id)

            chunks = self.splitter.split_documents(documents)
            if not chunks:
                return {
                    "success": False,
                    "document": {"filename": path.name, "file_path": str(path)},
                    "chunk_count": 0,
                    "error": "No chunks created - document may be empty",
                }

            self._add_documents_to_vector_store(chunks, source_id)

            return {
                "success": True,
                "document": {"filename": path.name, "file_path": str(path), "source_id": source_id},
                "chunk_count": len(chunks),
                "error": None,
            }

        except Exception as e:
            logger.error("Ingestion failed for %s: %s", file_path, e)
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
        source_id = source_id or f"text_{uuid.uuid4().hex[:12]}"
        logger.info("Ingesting text: %s", source_name)

        try:
            if self._check_existing(source_id) > 0:
                self.vector_store.delete_by_source(source_id)

            doc = Document(
                page_content=text,
                metadata={"source_id": source_id, "source_name": source_name, **(additional_metadata or {})},
            )
            chunks = self.splitter.split_documents([doc])
            if not chunks:
                return {
                    "success": False,
                    "source_id": source_id,
                    "chunk_count": 0,
                    "error": "No chunks created",
                }

            self._add_documents_to_vector_store(chunks, source_id)
            return {
                "success": True,
                "source_id": source_id,
                "source_name": source_name,
                "chunk_count": len(chunks),
                "error": None,
            }
        except Exception as e:
            logger.error("Text ingestion failed: %s", e)
            return {
                "success": False,
                "source_id": source_id,
                "chunk_count": 0,
                "error": str(e),
            }

    def _load_documents(self, file_path: str) -> List[Document]:
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext not in self.LOADER_MAP:
            supported = ", ".join(self.LOADER_MAP.keys())
            raise ValueError(f"Unsupported file type: {ext}. Supported: {supported}")

        loader_classes = self.LOADER_MAP[ext]
        last_error = None
        for loader_cls in loader_classes:
            try:
                loader = loader_cls(str(path))
                return loader.load()
            except Exception as e:
                last_error = e
                logger.warning("Loader %s failed for %s: %s", loader_cls.__name__, path.name, e)
        raise RuntimeError(f"All loaders failed for {path.name}: {last_error}")

    def _check_existing(self, source_id: str) -> int:
        """
        Check if a source has already been ingested.

        Args:
            source_id: Source document ID

        Returns:
            Number of existing chunks from this source
        """
        results = self.vector_store.store.get(where={"source_id": source_id}, include=[])
        ids = results.get("ids") if results else None
        return len(ids) if ids else 0

    def _add_documents_to_vector_store(self, docs: List[Document], source_id: str) -> None:
        texts = [doc.page_content for doc in docs]
        metadatas = [doc.metadata for doc in docs]
        ids = [f"{source_id}_{i}" for i in range(len(docs))]
        self.vector_store.add_documents(texts=texts, metadatas=metadatas, ids=ids)

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

    @staticmethod
    def _build_source_id(path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return f"{path.suffix.lstrip('.')}_{sha256_hash.hexdigest()[:12]}"
