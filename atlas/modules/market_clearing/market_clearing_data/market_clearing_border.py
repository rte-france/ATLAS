"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas.config import logger
from atlas.models.market.market_border import MarketBorder
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset


class MCBorder:
    def __init__(self, border: MarketBorder, input_dataset: MarketClearingInputDataset):
        self.border = border
        self.max_flow = None # extract TS
        self.min_flow = None # extract TS
        # TODO : extract ref_flow to update min and max flow

        self.has_loss_factor = True if self.border.loss_factor > 0 else False

        self.time_resolution = self.border.time_resolution if self.border.time_resolution else input_dataset.parameters.time_step
        # Check and adapt if needed the time resolution:
        if self.time_resolution < input_dataset.parameters.time_step:
            self.time_resolution = input_dataset.parameters.time_step
            logger.info(
                f"The time resolution of the border {self.border.name} has had to be adapted to the time step (it was smaller)."
            )
        else:
            n_time_steps, rest = divmod(self.time_resolution, input_dataset.parameters.time_step)
            if rest != 0.0:
                self.time_resolution = (n_time_steps + round(rest, 0)) * input_dataset.parameters.time_step
                logger.info(
                    f"The time resolution of the border {self.border.name} has had to be rounded according to the time step."
                )
        # TODO : Check link_generator