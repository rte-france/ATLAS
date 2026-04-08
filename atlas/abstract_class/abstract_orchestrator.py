from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic

from atlas.abstract_class.abstract_job import AbstractJob, J
from atlas.abstract_class.abstract_orchestrator_parameters import PO
from atlas.config import logger
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.timing import timer


class AbstractOrchestrator(ABC, Generic[PO, J]):
    """Placeholder abstract class for orchestrator."""

    parameters: PO

    @property
    @abstractmethod
    def jobs(self) -> list[J]:
        """
        Return jobs to execute.
        """

    # FIXME change log so Workflow doesn't appear
    def execute(self) -> CurrentInputState:
        """
        Execute the orchestrator

        Execute all orchestrator jobs sequentially.

        Each job receives as input the output of the previous job.
        The first job receives the orchestrator's initial dataset.

        If rollback_on_job_failure is enabled, the CIS will be automatically restored
        to its state before the failed job.
        """
        logger.info(f"Launching workflow : {self.parameters.name}")
        cis = CurrentInputState.from_directory(self.parameters.resolve_path(self.parameters.dataset_path))

        # Create initial snapshot if requested
        if self.parameters.create_job_snapshots:
            cis.create_snapshot("workflow_input")
            logger.debug("Created initial workflow snapshot")

        for job_idx, job in enumerate(self.jobs):
            logger.info(f"Launching job :'{job.name}' ({job_idx + 1}/{len(self.jobs)})")

            # Create snapshot before job if requested
            if self.parameters.create_job_snapshots:
                snapshot_name = f"input_{job.name}"
                cis.create_snapshot(snapshot_name)
                logger.debug(f"Created snapshot: {snapshot_name}")

            try:
                self._execute_job(job, cis)
            except Exception as e:
                logger.error(f"Job '{job.name}' failed: {e}")
                if self.parameters.rollback_on_job_failure:
                    logger.error(f"Current Input State automatically rolled back to state before '{job.name}'")

                # Show available snapshots for debugging
                if self.parameters.create_job_snapshots:
                    logger.info(f"Available snapshots: {cis.list_snapshots()}")

                raise RuntimeError(f"Workflow failed at job '{job.name}'") from e

            logger.info(f"Finishing job :'{job.name}'")

        # Export final orchestrator output
        logger.info("Exporting final workflow output")

        if self.parameters.export_output:
            cis.to_directory(self.parameters.resolve_path(self.parameters.output_dir) / "workflow_output")

        logger.info(f"Workflow '{self.parameters.name}' completed successfully")

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
        logger.info(f"Job '{job.name}' completed in {t()} seconds")

        output_dataset = job.output_dataset

        if not output_dataset:
            raise RuntimeError(f"Job {job.name} did not produce output_dataset")

        logger.debug("Applying all change sets to the current input state")
        # CISHandler will use transaction internally based on rollback_on_job_failure parameter
        CISHandler.apply(output_dataset.change_sets, cis, rollback_on_error=self.parameters.rollback_on_job_failure)

        if job.parameters.output.export_output_dataset:
            cis.to_directory(self.parameters.resolve_path(job.parameters.output.output_dir) / "output_dataset")
