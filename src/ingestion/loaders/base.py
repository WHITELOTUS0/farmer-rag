"""
Base classes for document loaders.

Defines the interface for all document loader implementations
and common data structures.
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional


@dataclass
class LoadedDocument:
    """
    Represents a loaded document with its content and metadata.

    Attributes:
        content: The extracted text content
        filename: Name of the source file
        source_type: File type (pdf, docx, txt)
        file_path: Original file path
        file_hash: SHA-256 hash of file content
        file_size: Size of file in bytes
        metadata: Additional metadata (page count, author, etc.)
    """
    content: str
    filename: str
    source_type: str
    file_path: str
    file_hash: str
    file_size: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_id(self) -> str:
        """Generate a unique source ID based on file hash."""
        return f"{self.source_type}_{self.file_hash[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "content": self.content,
            "filename": self.filename,
            "source_type": self.source_type,
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "source_id": self.source_id,
            "metadata": self.metadata,
        }


class BaseLoader(ABC):
    """
    Abstract base class for document loaders.

    All loader implementations should inherit from this class
    and implement the load method.
    """

    # File extensions this loader supports
    SUPPORTED_EXTENSIONS: list = []

    @abstractmethod
    def load(self, file_path: str) -> LoadedDocument:
        """
        Load a document from a file path.

        Args:
            file_path: Path to the document file

        Returns:
            LoadedDocument with extracted content and metadata

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file format is not supported
        """
        pass

    def can_load(self, file_path: str) -> bool:
        """
        Check if this loader can handle the given file.

        Args:
            file_path: Path to the document file

        Returns:
            True if this loader supports the file type
        """
        path = Path(file_path)
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def _compute_file_hash(self, file_path: str) -> str:
        """
        Compute SHA-256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _get_file_size(self, file_path: str) -> int:
        """
        Get file size in bytes.

        Args:
            file_path: Path to the file

        Returns:
            File size in bytes
        """
        return Path(file_path).stat().st_size

    def _validate_file(self, file_path: str) -> Path:
        """
        Validate that file exists and is supported.

        Args:
            file_path: Path to the file

        Returns:
            Path object

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file type not supported
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not self.can_load(file_path):
            raise ValueError(
                f"Unsupported file type: {path.suffix}. "
                f"Supported: {self.SUPPORTED_EXTENSIONS}"
            )

        return path
