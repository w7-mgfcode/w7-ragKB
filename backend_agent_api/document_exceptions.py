"""Custom exceptions for document operations.

Provides typed exceptions with HTTP status codes for document browser API.
"""


class DocumentError(Exception):
    """Base exception for document operations."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class DocumentNotFoundError(DocumentError):
    """Raised when a document or directory is not found."""

    def __init__(self, path: str):
        super().__init__(f"Document not found: {path}", status_code=404)
        self.path = path


class DocumentConflictError(DocumentError):
    """Raised when a document or directory already exists."""

    def __init__(self, path: str):
        super().__init__(f"Document already exists: {path}", status_code=409)
        self.path = path


class DocumentValidationError(DocumentError):
    """Raised when document input validation fails."""

    def __init__(self, message: str):
        super().__init__(f"Validation error: {message}", status_code=400)


class DirectoryNotEmptyError(DocumentError):
    """Raised when attempting to delete a non-empty directory."""

    def __init__(self, path: str):
        super().__init__(
            f"Directory not empty: {path}. Delete all contents first.",
            status_code=400
        )
        self.path = path


class SyncError(DocumentError):
    """Base exception for sync-related errors."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message, status_code)


class AtomicOperationError(SyncError):
    """Raised when an atomic operation fails and rollback is triggered."""

    def __init__(self, operation: str, file_path: str, original_error: Exception):
        self.operation = operation
        self.file_path = file_path
        self.original_error = original_error
        super().__init__(
            f"Atomic {operation} failed for {file_path}: {original_error}",
            status_code=500,
        )


class ReindexError(SyncError):
    """Raised when re-indexing fails."""

    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(
            f"Re-indexing failed for {file_path}: {reason}",
            status_code=500,
        )
