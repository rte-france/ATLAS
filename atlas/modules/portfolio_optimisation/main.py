"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import argparse

from atlas.io.input_loader import InputLoader
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.modules.portfolio_optimisation_legacy.parameters import PortfolioOptimizationParameters

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--parameters", type=str, required=True, help="Path to the yaml parameters file")
    parser.add_argument("--data", type=str, required=True, help="Path to the data directory")

    args = parser.parse_args()

    input_data_path = args.data
    raw_params_path = args.parameters
    params = PortfolioOptimizationParameters.from_file(raw_params_path)

    mc_module = PortfolioOptimisationModule()
    input_data = InputLoader.from_directory(input_data_path)
    mc_module.run(input_data, params)
