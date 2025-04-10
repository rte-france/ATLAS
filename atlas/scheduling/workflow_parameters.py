"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import yaml
from loguru import logger
from src.market_clearing.exports.parameters import MCExportParameters
from src.market_clearing.parameters import Parameters
from src.parameter_utils import ParameterUtils
from src.post_balancing_markets_aggregation.parameters import PostBalancingMarketParameters


class WorkflowParameters:
    datetime_format = "%d/%m/%Y %H:%M:%S"

    # Static list of all attributes:
    __slots__ = (
        "data_model_path",
        "files_path",
        "parameters_export",
        "parameters_market_clearing",
        "parameters_post_clearing",
    )

    def __init__(self, parameter_file):
        logger.info(f"parameters : {parameter_file}")
        # Open yaml configs file
        with open(parameter_file) as f:
            data = yaml.safe_load(f)

        self.files_path = ParameterUtils.parse_string(data["workflow_parameters"], "files_path")
        self.data_model_path = ParameterUtils.parse_string(
            data["workflow_parameters"],
            "data_model_path",
        )
        self.parameters_market_clearing = Parameters(
            Path(
                ParameterUtils.parse_string(
                    data["modules_parameters"],
                    "parameters_market_clearing",
                ),
            ),
        )
        self.parameters_post_clearing = PostBalancingMarketParameters(
            Path(
                ParameterUtils.parse_string(data["modules_parameters"], "parameters_post_clearing"),
            ),
        )
        self.parameters_export = MCExportParameters(
            Path(ParameterUtils.parse_string(data["modules_parameters"], "parameters_export")),
        )
