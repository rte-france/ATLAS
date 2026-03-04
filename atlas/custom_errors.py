from atlas.workflow.change_set import ChangeSet


class InputLoaderError(Exception):
    """Base exception for AtlasDataset errors."""

    pass


class DirectoryStructureError(InputLoaderError):
    """Raised when the input directory structure is invalid."""

    pass


class FileParsingError(InputLoaderError):
    """Raised when a file cannot be parsed correctly."""

    pass


class ObjectInstantiationError(InputLoaderError):
    """Raised when an object cannot be instantiated."""

    pass


class DataValidationError(InputLoaderError):
    """Raised when data validation fails."""

    pass


class ChangeSetApplicationError(Exception):
    """Raised when a change set fails to apply."""

    def __init__(self, message: str, change_set: ChangeSet, original_error: Exception):
        super().__init__(message)
        self.change_set = change_set
        self.original_error = original_error
