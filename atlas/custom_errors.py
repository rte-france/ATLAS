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
