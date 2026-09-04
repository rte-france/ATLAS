"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Border variable creation shared by the Clearing and ExchangesFixing phase models: both build the
same exchange/pos-exchange/neg-exchange variables, and the same shape of loss-related variables
(imports/exports/xsis/nus) — the only behavioural difference between the two phases being that
Clearing only creates the loss variables for borders with a non-zero loss factor, while
ExchangesFixing creates them unconditionally.
"""

from collections.abc import Callable
from typing import Protocol

import pendulum

import atlas.modules.market_clearing.constants as constants
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_border import DEFAULT_MAX_FLOW, DEFAULT_MIN_FLOW
from atlas.solver.solver_interface import OptimisationModel


class _BorderVariablePhase(Protocol):
    """Structural type for the Clearing/ExchangesFixing phase objects these helpers run against."""

    input_dataset: MarketClearingInputDataset
    model: OptimisationModel


def create_border_exchange_variables(phase: _BorderVariablePhase, is_atc: bool) -> None:
    for border_name, border in phase.input_dataset.market_borders.items():
        for time in phase.input_dataset.times:
            relative_max_flow = border.max_flow.get_value(time) if is_atc else float("inf")
            relative_min_flow = border.min_flow.get_value(time) if is_atc else float("-inf")
            phase.model.add_continuous_variable(
                constants.border_exchange_variable_name(border_name, time),
                relative_min_flow,
                relative_max_flow,
            )


def create_border_pos_exchanges_variables(phase: _BorderVariablePhase, is_atc: bool) -> None:
    for border_name, border in phase.input_dataset.market_borders.items():
        for time in phase.input_dataset.times:
            relative_max_flow = border.max_flow.get_value(time) if is_atc else DEFAULT_MAX_FLOW
            phase.model.add_continuous_variable(
                constants.border_pos_exchange_variable_name(border_name, time), 0.0, relative_max_flow
            )


def create_border_neg_exchanges_variables(phase: _BorderVariablePhase, is_atc: bool) -> None:
    for border_name, border in phase.input_dataset.market_borders.items():
        for time in phase.input_dataset.times:
            relative_min_flow = border.min_flow.get_value(time) if is_atc else DEFAULT_MIN_FLOW
            phase.model.add_continuous_variable(
                constants.border_neg_exchange_variable_name(border_name, time), relative_min_flow, 0.0
            )


def create_border_loss_variables(
    phase: _BorderVariablePhase,
    variable_name: Callable[[str, pendulum.DateTime], str],
    only_borders_with_losses: bool,
) -> None:
    for border_name, border in phase.input_dataset.market_borders.items():
        if only_borders_with_losses and not (border.loss_factor and border.loss_factor != 0.0):
            continue
        for time in phase.input_dataset.times:
            phase.model.add_continuous_variable(variable_name(border_name, time), -float("inf"), float("inf"))
