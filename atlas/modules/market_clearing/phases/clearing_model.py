"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import abstractmethod

from ortools.linear_solver import pywraplp

from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class ClearingModel:
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.solver = pywraplp.Solver.CreateSolver(parameters.solver_name)

        self.local_balances_var = None

    @abstractmethod
    def retrieve_solver_parameters(use_presolve: bool) -> pywraplp.MPSolverParameters:
        solver_params = pywraplp.MPSolverParameters()
        solver_params.PRESOLVE = int(use_presolve)
        return solver_params

    def create_variables(self) -> None:
        self.local_balances_var = self.create_local_balances_variables()

    def create_constraints(self) -> None:
        pass

    def create_objective_function(self) -> None:
        pass

    def create_local_balances_variables(self) -> dict[str, pywraplp.Solver.NumVar]:
        local_balances_var = {}
        for time_index in self.input_dataset.times:
            for market_area in self.input_dataset.market_areas:
                local_balances_var_name = ClearingModel.local_balances_variable_name(market_area.id, time_index)
                local_balances_var[local_balances_var_name] = self.solver.NumVar(
                    -float("inf"), float("inf"), local_balances_var_name
                )
        return local_balances_var

    @abstractmethod
    def local_balances_variable_name(area_id: int, time_index: int) -> str:
        return f"balance_on_{area_id}_at_{time_index}"
