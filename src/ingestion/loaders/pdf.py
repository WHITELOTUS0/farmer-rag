"""
PDF document loader.

Extracts text content from PDF files using pypdf library.
"""

import logging
from typing import Optional

from pypdf import PdfReader

from src.ingestion.loaders.base import BaseLoader, LoadedDocument

logger = logging.getLogger(__name__)


class PDFLoader(BaseLoader):
    """
    Loader for PDF documents.

    Uses pypdf for text extraction. Handles:
    - Multi-page documents
    - Basic metadata extraction (title, author, page count)
    - Text cleaning and normalization
    """

    SUPPORTED_EXTENSIONS = [".pdf"]

    def __init__(self, extract_images: bool = False):
        """
        Initialize the PDF loader.

        Args:
            extract_images: Whether to attempt image extraction (not implemented)
        """
        self.extract_images = extract_images

    def load(self, file_path: str) -> LoadedDocument:
        """
        Load a PDF document.

        Args:
            file_path: Path to the PDF file

        Returns:
            LoadedDocument with extracted text and metadata

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a PDF
        """
        path = self._validate_file(file_path)
        logger.info(f"Loading PDF: {path.name}")

        # Compute hash and size before reading
        file_hash = self._compute_file_hash(file_path)
        file_size = self._get_file_size(file_path)

        # Open and read PDF
        reader = PdfReader(file_path)

        # Extract text from all pages
        text_parts = []
        for page_num, page in enumerate(reader.pages, 1):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"Failed to extract text from page {page_num}: {e}")

        # Combine all text
        full_text = "\n\n".join(text_parts)

        # Clean the text
        full_text = self._clean_text(full_text)

        # Extract metadata
        metadata = self._extract_metadata(reader)
        metadata["page_count"] = len(reader.pages)

        return LoadedDocument(
            content=full_text,
            filename=path.name,
            source_type="pdf",
            file_path=str(path.absolute()),
            file_hash=file_hash,
            file_size=file_size,
            metadata=metadata,
        )

    def _extract_metadata(self, reader: PdfReader) -> dict:
        """
        Extract metadata from PDF.

        Args:
            reader: PdfReader instance

        Returns:
            Dictionary of metadata
        """
        metadata = {}

        try:
            pdf_metadata = reader.metadata
            if pdf_metadata:
                if pdf_metadata.title:
                    metadata["title"] = pdf_metadata.title
                if pdf_metadata.author:
                    metadata["author"] = pdf_metadata.author
                if pdf_metadata.subject:
                    metadata["subject"] = pdf_metadata.subject
                if pdf_metadata.creator:
                    metadata["creator"] = pdf_metadata.creator
                if pdf_metadata.creation_date:
                    metadata["creation_date"] = str(pdf_metadata.creation_date)
        except Exception as e:
            logger.warning(f"Failed to extract PDF metadata: {e}")

        return metadata

    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text.

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text
        """
        # Replace multiple spaces with single space
        import re
        text = re.sub(r' +', ' ', text)

        # Normalize line endings
        text = text.replace('\r\n', '\n')
        text = text.replace('\r', '\n')

        # Remove excessive newlines (keep max 2)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Fix common PDF extraction issues
        # - Hyphenated line breaks
        text = re.sub(r'-\n(\w)', r'\1', text)

        # Remove header/footer patterns (page numbers)
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
        text = re.sub(r'Page \d+ of \d+', '', text)

        return text.strip()

    def get_page_count(self, file_path: str) -> int:
        """
        Get the number of pages in a PDF.

        Args:
            file_path: Path to the PDF file

        Returns:
            Number of pages
        """
        reader = PdfReader(file_path)
        return len(reader.pages)

    def load_page(self, file_path: str, page_number: int) -> Optional[str]:
        """
        Load text from a specific page.

        Args:
            file_path: Path to the PDF file
            page_number: Page number (1-indexed)

        Returns:
            Text content of the page, or None if extraction fails
        """
        reader = PdfReader(file_path)

        if page_number < 1 or page_number > len(reader.pages):
            raise ValueError(
                f"Page number {page_number} out of range. "
                f"PDF has {len(reader.pages)} pages."
            )

        try:
            return reader.pages[page_number - 1].extract_text()
        except Exception as e:
            logger.warning(f"Failed to extract page {page_number}: {e}")
            return None
