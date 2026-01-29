"""Document loaders for various file formats."""

from src.ingestion.loaders.base import BaseLoader, LoadedDocument
from src.ingestion.loaders.pdf import PDFLoader
from src.ingestion.loaders.docx import DocxLoader

__all__ = [
    "BaseLoader",
    "LoadedDocument",
    "PDFLoader",
    "DocxLoader",
]
