import logging
from pathlib import Path

import yaml

from src.market_clearing.exports.parameters import MCExportParameters
from src.market_clearing.parameters import Parameters
from src.parameter_utils import ParameterUtils
from src.post_balancing_markets_aggregation.parameters import PostBalancingMarketParameters


class WorkflowParameters:
    datetime_format = "%d/%m/%Y %H:%M:%S"

    # Static list of all attributes:
    __slots__ = (
        "files_path",
        "data_model_path",
        "parameters_market_clearing",
        "parameters_post_clearing",
        "parameters_export",
    )

    def __init__(self, parameter_file):
        logging.info(f"parameters : {parameter_file}")
        # Open yaml configs file
        with open(parameter_file, "r") as f:
            data = yaml.safe_load(f)

        self.files_path = ParameterUtils.parse_string(data["workflow_parameters"], "files_path")
        self.data_model_path = ParameterUtils.parse_string(data["workflow_parameters"], "data_model_path")
        self.parameters_market_clearing = Parameters(
            Path(ParameterUtils.parse_string(data["modules_parameters"], "parameters_market_clearing")))
        self.parameters_post_clearing = PostBalancingMarketParameters(
            Path(ParameterUtils.parse_string(data["modules_parameters"], "parameters_post_clearing")))
        self.parameters_export = MCExportParameters(
            Path(ParameterUtils.parse_string(data["modules_parameters"], "parameters_export")))
