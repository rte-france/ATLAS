from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.enums import SolverStatus
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


class SolverError(RuntimeError):
    """Base exception for optimisation solver errors."""

    pass


class ModelNotSolvedError(SolverError):
    """Raised when a solution is read from a model that has never been solved."""

    pass


class UnsuccessfulSolveError(SolverError):
    """Raised when a solution is read from a model whose last solve did not succeed.

    OR-Tools returns ``0.0`` for every variable of an ``INFEASIBLE`` / ``UNBOUNDED`` / ``ABNORMAL``
    model instead of failing, so reading the solution would silently produce a plausible-looking
    but meaningless result.

    :param status: The status of the last solve
    :type status: SolverStatus
    :param model_name: Name of the optimisation model, when it has one
    :type model_name: str | None
    """

    def __init__(self, status: SolverStatus, model_name: str | None = None):
        model = f" '{model_name}'" if model_name else ""
        super().__init__(
            f"Optimisation model{model} has no usable solution: last solve finished with status "
            f"{status.name}. Reading the solution would return solver defaults, not optimisation results."
        )
        self.status = status
        self.model_name = model_name


class DataQualityWarning(UserWarning):
    """Warning for potential input data quality issues."""

    pass
