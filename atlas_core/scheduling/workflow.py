"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from src.api_marker import DynamicMarker

from atlas_core.scheduling.workflow_step import WorkflowStep


class Workflow:

    def __init__(self, name: str, data_model_path: str, input_marker_path: str, steps: list[WorkflowStep] = None):
        self.name = name
        self.data_model_path = data_model_path
        self.input_marker_path = input_marker_path
        if steps is None:
            self.steps = []
        else:
            self.steps = steps

    def add_step(self, step: WorkflowStep):
        self.steps.append(step)

    def add_steps(self, steps: list[WorkflowStep]):
        self.steps.extend(steps)

    def execute(self):
        output_marker = None
        first = True
        for step in self.steps:
            if first:
                first = False
                dynamic_marker = DynamicMarker("input", self.data_model_path)
                dynamic_marker.deserialize(self.input_marker_path)
                step.input_marker = dynamic_marker
                step.execute_step()
                output_marker = step.output_marker
            else:
                step.input_marker = output_marker
                step.execute_step()
