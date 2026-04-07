from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic

from atlas import AtlasDataset
from atlas.config import logger
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.timing import timer
from atlas.abstract_class.abstract_orchestrator_parameters import PO
from atlas.abstract_class.abstract_step import S


class AbstractOrchestrator(ABC, Generic[PO, S]):
    """Placeholder abstract class for orchestrator."""

    parameters: PO

    @property
    @abstractmethod
    def orchestrator_path(self) -> Path:
        """
        Return the path to the current orchestrator.
        """

    @property
    @abstractmethod
    def steps(self) -> list[S]:
        """
        Return steps to execute.
        """

    def execute(self) -> None:
        """
        Execute the orchestrator

        Execute all orchestrator steps sequentially.

        Each step receives as input the output of the previous step.
        The first step receives the orchestrator's initial dataset.
        """
        # TODO pass this log into the orchestrator
        # or just use the class running this execute
        # logger.info(f"Launching workflow : {self.parameters.name}")
        atlas_dataset = AtlasDataset.from_directory(self.orchestrator_path / self.parameters.dataset_path)
        cis = CurrentInputState(atlas_dataset)

        for step in self.steps:
            logger.info(f"Launching step :'{step.name}'")
            input_dataset = cis.filter_dataset(step.module.get_business_model_class_used(), step.module.get_filters())

            with timer() as t:
                step.run(input_dataset)
            logger.info(f"Step '{step.name}' completed in {t()} seconds")

            output_dataset = step.output_dataset

            if not output_dataset:
                raise RuntimeError(f"Step {step.name} did not produce output_dataset")

            logger.debug("Applying all change sets to the current input state")
            CISHandler.apply(output_dataset.change_sets, cis)
            if step.parameters.output.export_output_dataset:
                cis.data.to_directory(step.parameters.get_path(step.parameters.output.output_dir) / "output_dataset")

            logger.info(f"Finishing step :'{step.name}'")

        # TODO change name
        cis.to_directory(self.orchestrator_path / self.parameters.output_dir / "workflow_output")
