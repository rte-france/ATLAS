"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import importlib
import logging
from pathlib import Path
import yaml

from src.market_clearing.parameters import *

from atlas_core.scheduling.workflow import Workflow
from atlas_core.scheduling.workflow_step import WorkflowStep


class WorkflowFactory:

    def create_workflow(self, parameter_file: Path):
        '''
        Create a workflow object from a yml parameter file
        '''
        logging.info(f"workflow parameters : {parameter_file}")
        # Open yaml configs file
        with open(parameter_file, "r") as f:
            data = yaml.safe_load(f)

        workflow_parameters = data['workflow_parameters']
        files_path = workflow_parameters['files_path']
        data_model_path = workflow_parameters['data_model_path']
        input_marker_path = workflow_parameters['input_marker_path']

        steps = []
        for step_name, step in data['workflow'].items():
            module_class = self.instanciate_class_from_string(step['module'])
            parameters = step['parameters']
            parameters_class = self.instanciate_class_from_string(parameters['parser'])
            params = parameters_class(Path(parameters['file']))
            steps.append(WorkflowStep(step_name, params, module_class()))

        workflow = Workflow('wf', data_model_path, input_marker_path, steps)
        return workflow

    def instanciate_class_from_string(self, class_fullpath):
        '''
        Instanciate a class object from a string of its path. Example : src.market_clearing.market_clearing_main.MarketClearing
        '''
        module_name, class_name = class_fullpath.rsplit(".", 1)
        module_class = getattr(importlib.import_module(module_name), class_name)
        return  module_class

