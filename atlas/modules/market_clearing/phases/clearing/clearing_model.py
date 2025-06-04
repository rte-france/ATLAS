"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from ortools.linear_solver import pywraplp

from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.clearing.clearing_constraints import ClearingConstraints
from atlas.modules.market_clearing.phases.clearing.clearing_objective import ClearingObjective
from atlas.modules.market_clearing.phases.clearing.clearing_variables import ClearingVariables


class ClearingModel:
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.solver = None

    @staticmethod
    def create_solver_parameters(use_presolve: bool) -> pywraplp.MPSolverParameters:
        solver_params = pywraplp.MPSolverParameters()
        solver_params.PRESOLVE = int(use_presolve)
        return solver_params

    def build(self, solver_name):
        self.solver = pywraplp.Solver.CreateSolver(solver_name)
        self.create_variables()
        self.create_constraints()
        self.create_objective_function()

    def create_variables(self):
        ClearingVariables.build(self.solver, self.input_dataset, self.parameters)

    def create_constraints(self):
        ClearingConstraints.build(self.solver, self.input_dataset, self.parameters)

    def create_objective_function(self) -> ClearingObjective:
        clearing_objective  = ClearingObjective()
        clearing_objective.build()
        return clearing_objective

