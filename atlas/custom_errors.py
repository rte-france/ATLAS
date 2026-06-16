from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.orchestrator.change_set import ChangeSet

if TYPE_CHECKING:
    from atlas.io_utils.atlas_dataset import AtlasDataset
    from atlas.orchestrator.current_input_state import CurrentInputState


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


class WorkflowJobError(RuntimeError):
    """Raised when a workflow job fails.

    Always carries the rolled-back CIS (state before the failing job's changes
    were applied). When the failure occurs inside the module itself (job.run),
    also carries the input_dataset that was passed to the module.

    Example:
        >>> try:
        ...     cis = workflow.execute()
        ... except WorkflowJobError as e:
        ...     print(e.job_name)
        ...     e.cis.to_directory("debug/cis")         # pre-job state
        ...     if e.input_dataset:
        ...         e.input_dataset.to_directory("debug/input")  # module input
    """

    def __init__(
        self,
        message: str,
        job_name: str,
        cis: CurrentInputState,
        input_dataset: AtlasDataset | None = None,
    ):
        super().__init__(message)
        self.job_name = job_name
        self.cis = cis
        self.input_dataset = input_dataset

class DataQualityWarning(UserWarning):
    """Warning for potential input data quality issues."""

    pass
