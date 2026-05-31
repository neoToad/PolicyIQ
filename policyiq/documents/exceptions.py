"""Domain-specific exceptions for the documents app."""


class DocumentError(Exception):
    """Base exception for document pipeline errors."""


class ExtractionError(DocumentError):
    """Raised when PDF text extraction fails."""


class ChunkingError(DocumentError):
    """Raised when page chunking fails."""


class EmbeddingError(DocumentError):
    """Raised when the embedding service is unreachable or returns invalid data."""


class IndexingError(DocumentError):
    """Raised when ChromaDB indexing fails."""
