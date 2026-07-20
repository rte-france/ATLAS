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
from typing import Any, Protocol

import atlas.modules.market_clearing.constants as constants
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_border import DEFAULT_MAX_FLOW, DEFAULT_MIN_FLOW


class _BorderVariableModel(Protocol):
    """Structural type for the Clearing/ExchangesFixing phase models these helpers run against."""

    input_dataset: MarketClearingInputDataset

    def add_continuous_variable(self, name: str, lower_bound: float, upper_bound: float) -> Any: ...


def create_border_exchange_variables(model: _BorderVariableModel, is_atc: bool) -> None:
    for border_name, mc_border in model.input_dataset.mc_market_borders.items():
        for time_index, _time in enumerate(model.input_dataset.times):
            relative_max_flow = mc_border.max_flow.get_value(_time) if is_atc else float("inf")
            relative_min_flow = mc_border.min_flow.get_value(_time) if is_atc else float("-inf")
            model.add_continuous_variable(
                constants.border_exchange_variable_name(border_name, time_index),
                relative_min_flow,
                relative_max_flow,
            )


def create_border_pos_exchanges_variables(model: _BorderVariableModel, is_atc: bool) -> None:
    for border_name, mc_border in model.input_dataset.mc_market_borders.items():
        for time_index, _time in enumerate(model.input_dataset.times):
            relative_max_flow = mc_border.max_flow.get_value(_time) if is_atc else DEFAULT_MAX_FLOW
            model.add_continuous_variable(
                constants.border_pos_exchange_variable_name(border_name, time_index), 0.0, relative_max_flow
            )


def create_border_neg_exchanges_variables(model: _BorderVariableModel, is_atc: bool) -> None:
    for border_name, mc_border in model.input_dataset.mc_market_borders.items():
        for time_index, _time in enumerate(model.input_dataset.times):
            relative_min_flow = mc_border.min_flow.get_value(_time) if is_atc else DEFAULT_MIN_FLOW
            model.add_continuous_variable(
                constants.border_neg_exchange_variable_name(border_name, time_index), relative_min_flow, 0.0
            )


def create_border_loss_variables(
    model: _BorderVariableModel,
    variable_name: Callable[[str, int], str],
    only_borders_with_losses: bool,
) -> None:
    for border_name, mc_border in model.input_dataset.mc_market_borders.items():
        if only_borders_with_losses and not (mc_border.loss_factor and mc_border.loss_factor != 0.0):
            continue
        for time_index, _ in enumerate(model.input_dataset.times):
            model.add_continuous_variable(variable_name(border_name, time_index), -float("inf"), float("inf"))
