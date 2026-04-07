from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic

from atlas.abstract_class.abstract_orchestrator_parameters import PO
from atlas.abstract_class.abstract_step import AbstractJob, S
from atlas.config import logger
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.timing import timer


class AbstractOrchestrator(ABC, Generic[PO, S]):
    """Placeholder abstract class for orchestrator."""

    parameters: PO

    @property
    @abstractmethod
    def jobs(self) -> list[S]:
        """
        Return steps to execute.
        """

    # FIXME change log so Workflow doesn't appear
    def execute(self) -> CurrentInputState:
        """
        Execute the workflow

        Execute all workflow steps sequentially.

        Each job receives as input the output of the previous job.
        The first job receives the workflow's initial dataset.

        If rollback_on_step_failure is enabled, the CIS will be automatically restored
        to its state before the failed job.
        """
        logger.info(f"Launching workflow : {self.parameters.name}")
        cis = CurrentInputState.from_directory(self.parameters.resolve_path(self.parameters.dataset_path))

        # Create initial snapshot if requested
        if self.parameters.create_step_snapshots:
            cis.create_snapshot("workflow_input")
            logger.debug("Created initial workflow snapshot")

        for step_idx, step in enumerate(self.jobs):
            logger.info(f"Launching job :'{step.name}' ({step_idx + 1}/{len(self.jobs)})")

            # Create snapshot before job if requested
            if self.parameters.create_step_snapshots:
                snapshot_name = f"input_{step.name}"
                cis.create_snapshot(snapshot_name)
                logger.debug(f"Created snapshot: {snapshot_name}")

            try:
                self._execute_step(step, cis)
            except Exception as e:
                logger.error(f"Step '{step.name}' failed: {e}")
                if self.parameters.rollback_on_step_failure:
                    logger.error(f"Current Input State automatically rolled back to state before '{step.name}'")

                # Show available snapshots for debugging
                if self.parameters.create_step_snapshots:
                    logger.info(f"Available snapshots: {cis.list_snapshots()}")

                raise RuntimeError(f"Workflow failed at job '{step.name}'") from e

            logger.info(f"Finishing job :'{step.name}'")

        # Export final workflow output
        logger.info("Exporting final workflow output")

        if self.parameters.export_output:
            cis.to_directory(self.parameters.resolve_path(self.parameters.output_dir) / "workflow_output")

        logger.info(f"Workflow '{self.parameters.name}' completed successfully")

        if self.parameters.create_step_snapshots:
            logger.info(f"Snapshots created: {cis.list_snapshots()}")

        return cis

    def _execute_step(self, step: AbstractJob, cis: CurrentInputState):
        """Execute a single job.

        :param step: The job to execute
        :type step: AbstractJob
        :param cis: The current input state
        :type cis: CurrentInputState
        """
        input_dataset = cis.filter_dataset(step.module.get_business_model_class_used(), step.module.get_filters())

        with timer() as t:
            step.run(input_dataset)
        logger.info(f"Step '{step.name}' completed in {t()} seconds")

        output_dataset = step.output_dataset

        if not output_dataset:
            raise RuntimeError(f"Step {step.name} did not produce output_dataset")

        logger.debug("Applying all change sets to the current input state")
        # CISHandler will use transaction internally based on rollback_on_step_failure parameter
        CISHandler.apply(output_dataset.change_sets, cis, rollback_on_error=self.parameters.rollback_on_step_failure)

        if step.parameters.output.export_output_dataset:
            cis.to_directory(self.parameters.resolve_path(step.parameters.output.output_dir) / "output_dataset")
