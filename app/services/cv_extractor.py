"""
CV/Resume text extraction utilities.
Supports PDF and DOCX files.
"""

import io
from typing import BinaryIO


class CVTextExtractor:
    """Extract text from CV/Resume files (PDF, DOCX)."""

    def extract_text(self, file_content: bytes, filename: str) -> str:
        """
        Extract text from a CV file.

        Args:
            file_content: The file content as bytes
            filename: Original filename (used to detect file type)

        Returns:
            Extracted text content

        Raises:
            ValueError: If file format is not supported
        """
        filename_lower = filename.lower()

        if filename_lower.endswith('.pdf'):
            return self._extract_from_pdf(file_content)
        elif filename_lower.endswith('.docx'):
            return self._extract_from_docx(file_content)
        elif filename_lower.endswith('.doc'):
            raise ValueError("Old .doc format not supported. Please convert to PDF or DOCX.")
        else:
            raise ValueError(f"Unsupported file format: {filename}. Only PDF and DOCX are supported.")

    def _extract_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF using pypdf."""
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_content))
        text_parts = []

        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                text_parts.append(text.strip())

        return "\n\n".join(text_parts)

    def _extract_from_docx(self, file_content: bytes) -> str:
        """Extract text from DOCX using python-docx."""
        from docx import Document

        document = Document(io.BytesIO(file_content))
        text_parts = []

        for paragraph in document.paragraphs:
            if paragraph.text and paragraph.text.strip():
                text_parts.append(paragraph.text.strip())

        return "\n\n".join(text_parts)

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
        """
        Split text into smaller chunks for embedding.

        Args:
            text: Text to chunk
            chunk_size: Maximum characters per chunk
            overlap: Overlap between chunks

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        chunks = []
        lines = text.split('\n')
        current_chunk = []

        for line in lines:
            if len('\n'.join(current_chunk) + '\n' + line) > chunk_size:
                if current_chunk:
                    chunks.append('\n'.join(current_chunk).strip())
                    current_chunk = [line[-overlap:]] if len(line) > overlap else []
                else:
                    chunks.append(line.strip())
                    current_chunk = []
            else:
                current_chunk.append(line)

        if current_chunk:
            chunk_text = '\n'.join(current_chunk).strip()
            if chunk_text:
                chunks.append(chunk_text)

        return [c for c in chunks if c and len(c) > 50]


def get_cv_extractor() -> CVTextExtractor:
    """Dependency injection for CV extractor."""
    return CVTextExtractor()