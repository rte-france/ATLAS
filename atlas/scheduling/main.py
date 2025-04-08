"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import logging
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

from .workflow_factory import WorkflowFactory

if __name__ == "__main__":
    start = datetime.now()
    print(start)

    parser = ArgumentParser()
    parser.add_argument(
        "--log_level",
        type=str.upper,
        help="Log level to be displayed",
        required=False,
        default="INFO",
    )
    parser.add_argument(
        "--wf_parameters",
        type=str,
        help="workflow parameters",
        required=True,
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.getLevelName(args.log_level))

    workflow = WorkflowFactory().create_workflow(Path(args.wf_parameters))
    workflow.execute()

    end = datetime.now()
    print(end)
    diff = end - start
    print(diff.total_seconds())