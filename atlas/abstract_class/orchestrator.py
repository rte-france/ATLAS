from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Generic

import yaml

from atlas.abstract_class.dataset import AbstractDataset
from atlas.abstract_class.job import AbstractJob, J
from atlas.abstract_class.orchestrator_parameters import PO
from atlas.config import logger
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.timing import timer


class AbstractOrchestrator(ABC, Generic[PO, J]):
    """Placeholder abstract class for orchestrator."""

    parameters: PO
    final_dataset: AbstractDataset | None = None
    generic_module_parameters: dict[str, Any]

    @property
    @abstractmethod
    def jobs(self) -> Iterator[J]:
        """
        Return jobs to execute.
        """

    @property
    @abstractmethod
    def jobs_count(self) -> int:
        """
        Return the number of jobs to execute.
        """

    def build_generic_module_parameters(self):
        """
        Build the generic module parameters used by this orchestrator.
        """
        if self.parameters.parameters_path:
            with open(self.parameters.resolve_path(self.parameters.parameters_path)) as file:
                self.generic_module_parameters = yaml.safe_load(file)
        else:
            self.generic_module_parameters = {}

    def build_module_parameters(self, parameters_path: Path) -> dict[str, Any]:
        """
        Build the module parameters using the generic module parameters from this orchestrator
        and the parameters in the file from the given path.
        """
        # FIXME the function called has to be removed, the static function code should replace the call we do here
        return AbstractOrchestrator.static_build_module_parameters(self.generic_module_parameters, parameters_path)

    # FIXME this static function is temporary as it would break some unit tests
    # These unit tests must be adapter to test the "non-static" version of this function from Orchestrator
    @staticmethod
    def static_build_module_parameters(parameters: dict[str, Any], parameters_path: Path) -> dict[str, Any]:
        """
        Build the module parameters using the generic module parameters from this orchestrator
        and the parameters in the file from the given path.
        """
        parameters = copy.deepcopy(parameters)
        with open(parameters_path) as file:
            custom_parameters = yaml.safe_load(file)
        parameters.update(custom_parameters)
        return parameters

    def get_output_dataset(self) -> AbstractDataset | None:
        """
        Returns the final dataset of the workflow, return None if the orchestrator hasn't been executed to the end.
        """
        return self.final_dataset

    def execute(self) -> CurrentInputState:
        """
        Execute the orchestrator

        Execute all orchestrator jobs sequentially.

        Each job receives as input the output of the previous job.
        The first job receives the orchestrator's initial dataset.

        If rollback_on_job_failure is enabled, the CIS will be automatically restored
        to its state before the failed job.
        """
        logger.info(f"Launching {self.__class__.__name__} : {self.parameters.name}")
        cis = CurrentInputState.from_directory(self.parameters.resolve_path(self.parameters.dataset_path))

        # Create initial snapshot if requested
        if self.parameters.create_job_snapshots:
            cis.create_snapshot(f"{self.__class__.__name__}_input")
            logger.debug(f"Created initial {self.__class__.__name__} snapshot")

        for job_idx, job in enumerate(self.jobs):
            logger.info(f"Launching :'{job.name}' ({job_idx + 1}/{self.jobs_count})")

            # Create snapshot before job if requested
            if self.parameters.create_job_snapshots:
                snapshot_name = f"input_{job.name}"
                cis.create_snapshot(snapshot_name)
                logger.debug(f"Created snapshot: {snapshot_name}")

            try:
                self._execute_job(job, cis)
            except Exception as e:
                logger.error(f"{job}' failed: {e}")
                if self.parameters.rollback_on_job_failure:
                    logger.error(f"Current Input State automatically rolled back to state before '{job}'")

                # Show available snapshots for debugging
                if self.parameters.create_job_snapshots:
                    logger.info(f"Available snapshots: {cis.list_snapshots()}")

                raise RuntimeError(f"{self.__class__.__name__} failed at job '{job}'") from e

            logger.info(f"Finishing job :'{job.name}'")

            if job_idx + 1 == self.jobs_count:
                self.final_dataset = job.output_dataset

        # Export final orchestrator output
        logger.info(f"Exporting final {self.__class__.__name__} output")

        if self.parameters.export_output:
            cis.to_directory(
                self.parameters.resolve_path(self.parameters.output_dir) / f"{self.__class__.__name__}_output"
            )

        logger.info(f"{self.__class__.__name__} '{self.parameters.name}' completed successfully")

        if self.parameters.create_job_snapshots:
            logger.info(f"Snapshots created: {cis.list_snapshots()}")

        return cis

    def _execute_job(self, job: AbstractJob, cis: CurrentInputState):
        """Execute a single job.

        :param job: The job to execute
        :type job: AbstractJob
        :param cis: The current input state
        :type cis: CurrentInputState
        """
        input_dataset = cis.filter_dataset(job.module.get_business_model_class_used(), job.module.get_filters())

        with timer() as t:
            job.run(input_dataset)
        logger.info(f"'{job.name}' completed in {t()} seconds")

        output_dataset = job.output_dataset

        if not output_dataset:
            raise RuntimeError(f"{job} did not produce output_dataset")

        logger.debug("Applying all change sets to the current input state")
        # CISHandler will use transaction internally based on rollback_on_job_failure parameter
        CISHandler.apply(output_dataset.change_sets, cis, rollback_on_error=self.parameters.rollback_on_job_failure)

        if job.parameters.output.export_output_dataset:
            cis.to_directory(self.parameters.resolve_path(job.parameters.output.output_dir) / "output_dataset")
