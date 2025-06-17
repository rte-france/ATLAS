"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.io.input_loader import InputLoader
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.modules.portfolio_optimisation_legacy.parameters import PortfolioOptimisationParameters


def _portfolio_optimisation(
    parameters: str,
    data: str,
):
    """
    Run the Portfolio Optimisation module.

    :param parameters: Path to the YAML parameters file containing optimisation settings.
    :type parameters: str
    :param data: Path to the data directory containing input data for the optimisation.
    :type data: str
    """
    params = PortfolioOptimisationParameters.from_file(parameters)
    module = PortfolioOptimisationModule()
    input_data = InputLoader.from_directory(data)
    module.run(input_data, params)
