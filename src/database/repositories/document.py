"""
Repository for Document database operations.

Tracks ingested documents, their processing status,
and metadata for admin management.
"""

import uuid
from typing import Optional, List
from datetime import datetime

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Document, DocumentStatus


class DocumentRepository:
    """Repository for document-related database operations."""

    def __init__(self, session: AsyncSession):
        """
        Initialize the repository with a database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_document(
        self,
        filename: str,
        source_type: str,
        source_url: Optional[str] = None,
        drive_file_id: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        file_hash: Optional[str] = None,
    ) -> Document:
        """
        Create a new document record.

        Args:
            filename: Name of the document file
            source_type: File type (pdf, docx, txt)
            source_url: URL where the document came from
            drive_file_id: Google Drive file ID if synced from Drive
            file_size_bytes: Size of the file
            file_hash: SHA-256 hash of the file content

        Returns:
            Document: Created document instance
        """
        document = Document(
            filename=filename,
            source_type=source_type,
            source_url=source_url,
            drive_file_id=drive_file_id,
            file_size_bytes=file_size_bytes,
            file_hash=file_hash,
            status=DocumentStatus.PENDING,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def get_document_by_id(
        self,
        document_id: uuid.UUID,
    ) -> Optional[Document]:
        """
        Get a document by its ID.

        Args:
            document_id: UUID of the document

        Returns:
            Document or None if not found
        """
        query = select(Document).where(Document.id == document_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_document_by_hash(
        self,
        file_hash: str,
    ) -> Optional[Document]:
        """
        Get a document by its content hash.

        Useful for checking if a document has already been ingested.

        Args:
            file_hash: SHA-256 hash of the file content

        Returns:
            Document or None if not found
        """
        query = select(Document).where(Document.file_hash == file_hash)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_document_by_drive_id(
        self,
        drive_file_id: str,
    ) -> Optional[Document]:
        """
        Get a document by its Google Drive file ID.

        Args:
            drive_file_id: Google Drive file ID

        Returns:
            Document or None if not found
        """
        query = select(Document).where(Document.drive_file_id == drive_file_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all_documents(
        self,
        status: Optional[DocumentStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Document]:
        """
        Get all documents with optional status filter.

        Args:
            status: Optional status filter
            limit: Maximum number of documents to return
            offset: Number of documents to skip

        Returns:
            List of Document instances
        """
        query = select(Document).limit(limit).offset(offset)

        if status:
            query = query.where(Document.status == status)

        query = query.order_by(Document.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_document_status(
        self,
        document_id: uuid.UUID,
        status: DocumentStatus,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Document]:
        """
        Update document processing status.

        Args:
            document_id: UUID of the document
            status: New status
            chunk_count: Number of chunks created (for completed status)
            error_message: Error message (for failed status)
            metadata: Extracted metadata

        Returns:
            Updated Document or None if not found
        """
        update_values = {"status": status}

        if status == DocumentStatus.COMPLETED:
            update_values["processed_at"] = datetime.utcnow()

        if chunk_count is not None:
            update_values["chunk_count"] = chunk_count

        if error_message is not None:
            update_values["error_message"] = error_message

        if metadata is not None:
            update_values["extra_metadata"] = metadata

        stmt = (
            update(Document)
            .where(Document.id == document_id)
            .values(**update_values)
            .returning(Document)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_documents(self) -> List[Document]:
        """
        Get all documents pending processing.

        Returns:
            List of pending Document instances
        """
        return await self.get_all_documents(status=DocumentStatus.PENDING)

    async def get_document_stats(self) -> dict:
        """
        Get document statistics for the admin dashboard.

        Returns:
            Dictionary with document statistics
        """
        # Total count by status
        status_counts = {}
        for status in DocumentStatus:
            query = select(func.count(Document.id)).where(
                Document.status == status
            )
            result = await self.session.execute(query)
            status_counts[status.value] = result.scalar() or 0

        # Total chunks
        chunk_query = select(func.sum(Document.chunk_count))
        chunk_result = await self.session.execute(chunk_query)
        total_chunks = chunk_result.scalar() or 0

        # Total file size
        size_query = select(func.sum(Document.file_size_bytes))
        size_result = await self.session.execute(size_query)
        total_size = size_result.scalar() or 0

        return {
            "status_counts": status_counts,
            "total_documents": sum(status_counts.values()),
            "total_chunks": total_chunks,
            "total_size_mb": round(total_size / (1024 * 1024), 2) if total_size else 0,
        }

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        """
        Delete a document record.

        Note: This only deletes the database record, not the vectors in ChromaDB.
        The vector store cleanup should be handled separately.

        Args:
            document_id: UUID of the document to delete

        Returns:
            True if deleted, False if not found
        """
        document = await self.get_document_by_id(document_id)
        if document:
            await self.session.delete(document)
            return True
        return False
