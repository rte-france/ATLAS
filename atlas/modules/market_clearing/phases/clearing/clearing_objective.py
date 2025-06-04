"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.clearing.clearing_variables import ClearingVariables


class ClearingObjective:
    def __init__(self):
        self.objective = None
        self.accepted_powers = None
        self.global_exchanges = None
        self.max_exchanges = None
        self.min_exchanges = None

    @staticmethod
    def build(solver, input_dataset: MarketClearingInputDataset, parameters : MarketClearingParameters):
        """ Create objective function for the clearing phase model"""
        objective = ClearingObjective.add_accepted_powers(input_dataset, parameters.price_modifier_lambda_1)
        if parameters.flow_penalty_lambda_2 != 0.0:
            objective -= ClearingObjective.add_global_exchanges()
        if parameters.exchanges_constraint == "atc":
            if parameters.flow_penalty_lambda_3 != 0.0:
                objective -= ClearingObjective.add_max_exchanges()
            if parameters.flow_penalty_lambda_4 != 0.0:
                objective -= ClearingObjective.add_min_exchanges()
        solver.Maximise(objective)

    @staticmethod
    def add_accepted_powers(input_dataset: MarketClearingInputDataset, lambda1: float):
        objective = 0.0
        for area in input_dataset.mc_market_areas:
            for order in area.orders:
                accepted_power = ClearingVariables.accepted_power_variable_name(order.order.name)
                altered_price = order.order.price - order.production_sign * lambda1
                objective -= order.production_sign * altered_price * order.duration * accepted_power / 60
        return objective

    @staticmethod
    def add_global_exchanges():
        pass

    @staticmethod
    def add_max_exchanges():
        pass

    @staticmethod
    def add_min_exchanges():
        pass
