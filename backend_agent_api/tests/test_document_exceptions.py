"""Unit tests for document exception classes."""

import pytest


class TestDocumentError:
    """Tests for the base DocumentError class."""

    def test_default_status_code(self):
        """Test that DocumentError has default status code 500."""
        from document_exceptions import DocumentError

        error = DocumentError("Something went wrong")
        assert error.status_code == 500
        assert error.detail == "Something went wrong"

    def test_custom_status_code(self):
        """Test that DocumentError accepts custom status code."""
        from document_exceptions import DocumentError

        error = DocumentError("Custom error", status_code=418)
        assert error.status_code == 418
        assert error.detail == "Custom error"

    def test_is_exception(self):
        """Test that DocumentError is an Exception."""
        from document_exceptions import DocumentError

        error = DocumentError("Test")
        assert isinstance(error, Exception)

    def test_str_representation(self):
        """Test that DocumentError has correct string representation."""
        from document_exceptions import DocumentError

        error = DocumentError("Test error")
        assert str(error) == "Test error"


class TestDocumentNotFoundError:
    """Tests for DocumentNotFoundError."""

    def test_status_code(self):
        """Test that DocumentNotFoundError has status code 404."""
        from document_exceptions import DocumentNotFoundError

        error = DocumentNotFoundError()
        assert error.status_code == 404

    def test_default_message(self):
        """Test default error message."""
        from document_exceptions import DocumentNotFoundError

        error = DocumentNotFoundError()
        assert error.detail == "Document not found"

    def test_custom_message(self):
        """Test custom error message."""
        from document_exceptions import DocumentNotFoundError

        error = DocumentNotFoundError("File 'test.md' not found")
        assert error.detail == "File 'test.md' not found"
        assert error.status_code == 404

    def test_inherits_from_document_error(self):
        """Test that DocumentNotFoundError inherits from DocumentError."""
        from document_exceptions import DocumentError, DocumentNotFoundError

        error = DocumentNotFoundError()
        assert isinstance(error, DocumentError)
        assert isinstance(error, Exception)


class TestDocumentConflictError:
    """Tests for DocumentConflictError."""

    def test_status_code(self):
        """Test that DocumentConflictError has status code 409."""
        from document_exceptions import DocumentConflictError

        error = DocumentConflictError()
        assert error.status_code == 409

    def test_default_message(self):
        """Test default error message."""
        from document_exceptions import DocumentConflictError

        error = DocumentConflictError()
        assert error.detail == "Document already exists"

    def test_custom_message(self):
        """Test custom error message."""
        from document_exceptions import DocumentConflictError

        error = DocumentConflictError("File 'test.md' already exists in this directory")
        assert error.detail == "File 'test.md' already exists in this directory"
        assert error.status_code == 409

    def test_inherits_from_document_error(self):
        """Test that DocumentConflictError inherits from DocumentError."""
        from document_exceptions import DocumentConflictError, DocumentError

        error = DocumentConflictError()
        assert isinstance(error, DocumentError)
        assert isinstance(error, Exception)


class TestDocumentValidationError:
    """Tests for DocumentValidationError."""

    def test_status_code(self):
        """Test that DocumentValidationError has status code 400."""
        from document_exceptions import DocumentValidationError

        error = DocumentValidationError()
        assert error.status_code == 400

    def test_default_message(self):
        """Test default error message."""
        from document_exceptions import DocumentValidationError

        error = DocumentValidationError()
        assert error.detail == "Invalid document data"

    def test_custom_message(self):
        """Test custom error message."""
        from document_exceptions import DocumentValidationError

        error = DocumentValidationError("Filename contains invalid characters: '../etc/passwd'")
        assert error.detail == "Filename contains invalid characters: '../etc/passwd'"
        assert error.status_code == 400

    def test_inherits_from_document_error(self):
        """Test that DocumentValidationError inherits from DocumentError."""
        from document_exceptions import DocumentError, DocumentValidationError

        error = DocumentValidationError()
        assert isinstance(error, DocumentError)
        assert isinstance(error, Exception)


class TestDirectoryNotEmptyError:
    """Tests for DirectoryNotEmptyError."""

    def test_status_code(self):
        """Test that DirectoryNotEmptyError has status code 400."""
        from document_exceptions import DirectoryNotEmptyError

        error = DirectoryNotEmptyError()
        assert error.status_code == 400

    def test_default_message(self):
        """Test default error message."""
        from document_exceptions import DirectoryNotEmptyError

        error = DirectoryNotEmptyError()
        assert error.detail == "Directory is not empty"

    def test_custom_message(self):
        """Test custom error message."""
        from document_exceptions import DirectoryNotEmptyError

        error = DirectoryNotEmptyError("Cannot delete 'docs/': contains 5 files")
        assert error.detail == "Cannot delete 'docs/': contains 5 files"
        assert error.status_code == 400

    def test_inherits_from_document_error(self):
        """Test that DirectoryNotEmptyError inherits from DocumentError."""
        from document_exceptions import DirectoryNotEmptyError, DocumentError

        error = DirectoryNotEmptyError()
        assert isinstance(error, DocumentError)
        assert isinstance(error, Exception)


class TestExceptionRaising:
    """Tests for raising and catching exceptions."""

    def test_can_raise_and_catch_document_error(self):
        """Test that DocumentError can be raised and caught."""
        from document_exceptions import DocumentError

        with pytest.raises(DocumentError) as exc_info:
            raise DocumentError("Test error")
        assert exc_info.value.detail == "Test error"
        assert exc_info.value.status_code == 500

    def test_can_catch_specific_exception_as_base(self):
        """Test that specific exceptions can be caught as DocumentError."""
        from document_exceptions import DocumentError, DocumentNotFoundError

        with pytest.raises(DocumentError):
            raise DocumentNotFoundError("Not found")

    def test_can_catch_specific_exception_by_type(self):
        """Test that specific exceptions can be caught by their type."""
        from document_exceptions import DocumentNotFoundError

        with pytest.raises(DocumentNotFoundError) as exc_info:
            raise DocumentNotFoundError("File missing")
        assert exc_info.value.status_code == 404

    def test_exception_attributes_accessible_after_catch(self):
        """Test that exception attributes are accessible after catching."""
        from document_exceptions import DocumentConflictError, DocumentError

        try:
            raise DocumentConflictError("Duplicate file")
        except DocumentError as e:
            assert e.status_code == 409
            assert e.detail == "Duplicate file"
