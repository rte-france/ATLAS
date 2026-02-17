"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import argparse

from atlas.workflow.workflow import Workflow
from atlas.workflow.workflow_parameters import WorkflowParametersParser

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--parameters", type=str, required=True, help="Path to the yaml parameters file")

    args = parser.parse_args()

    workflow_params_path = args.parameters

    workflow_parameters = WorkflowParametersParser.from_file(workflow_params_path)

    workflow = Workflow(workflow_parameters)
    workflow.build_generic_module_parameters()
    workflow.build_steps()
    workflow.execute()
