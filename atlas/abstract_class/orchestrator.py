from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Generic

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
