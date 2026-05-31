"""Domain-specific exceptions for the queries app."""


class QueryError(Exception):
    """Base exception for query pipeline errors."""


class RetrievalError(QueryError):
    """Raised when vector retrieval fails."""


class GenerationError(QueryError):
    """Raised when the LLM generation service fails."""
