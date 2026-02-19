"""
Database-backed ingestion pipeline using pgvector.
"""

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredFileLoader,
)
from langchain_core.documents import Document as LC_Document
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Document, DocumentChunk, DocumentStatus
from src.retrieval.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class DatabaseIngestionPipeline:
    """Ingest documents and store chunks in Postgres + pgvector."""

    LOADER_MAP = {
        ".pdf": [PyPDFLoader],
        ".docx": [Docx2txtLoader, UnstructuredFileLoader],
        ".txt": [TextLoader],
    }

    def __init__(self, splitter: Optional[object] = None):
        self.embedding_service = EmbeddingService()
        self.splitter = splitter or SemanticChunker(
            self.embedding_service.embeddings,
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=0.8,
        )

    async def ingest_file(
        self,
        db: AsyncSession,
        file_path: str,
        filename: Optional[str] = None,
        source_url: Optional[str] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        path = Path(file_path)
        filename = filename or path.name

        file_hash = self._hash_file(file_path)
        file_size = path.stat().st_size if path.exists() else None

        doc = Document(
            filename=filename,
            source_type=path.suffix.lower().lstrip("."),
            source_url=source_url,
            status=DocumentStatus.PROCESSING,
            chunk_count=0,
            extra_metadata=additional_metadata or {},
            file_size_bytes=file_size,
            file_hash=file_hash,
        )
        db.add(doc)
        await db.flush()

        try:
            documents = self._load_documents(file_path)
            if not documents:
                doc.status = DocumentStatus.FAILED
                doc.error_message = "No documents loaded"
                await db.flush()
                return {"success": False, "document_id": str(doc.id), "error": doc.error_message}

            for item in documents:
                item.metadata.update(
                    {
                        "source_id": str(doc.id),
                        "source_name": filename,
                        **(additional_metadata or {}),
                    }
                )

            chunks = self.splitter.split_documents(documents)
            if not chunks:
                doc.status = DocumentStatus.FAILED
                doc.error_message = "No chunks created"
                await db.flush()
                return {"success": False, "document_id": str(doc.id), "error": doc.error_message}

            texts = [chunk.page_content for chunk in chunks]
            metadatas = [chunk.metadata for chunk in chunks]
            embeddings = self.embedding_service.embed_documents(texts)

            for text, metadata, embedding in zip(texts, metadatas, embeddings):
                db.add(
                    DocumentChunk(
                        document_id=doc.id,
                        content=text,
                        embedding=embedding,
                        extra_metadata=metadata,
                    )
                )

            doc.chunk_count = len(chunks)
            doc.status = DocumentStatus.COMPLETED
            doc.processed_at = datetime.utcnow()
            await db.flush()

            return {
                "success": True,
                "document_id": str(doc.id),
                "chunk_count": len(chunks),
                "filename": filename,
            }
        except Exception as exc:
            logger.error("Ingestion failed for %s: %s", filename, exc)
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(exc)
            await db.flush()
            return {"success": False, "document_id": str(doc.id), "error": str(exc)}

    def _load_documents(self, file_path: str) -> List[LC_Document]:
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
            except Exception as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        return []

    def _hash_file(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
