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

from dataclasses import dataclass, field

from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_border import DEFAULT_MAX_FLOW, DEFAULT_MIN_FLOW
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.temporal_variable import TemporalVariable


@dataclass
class BorderVariables:
    """Temporal variables of the market borders, each family keyed by border name.

    A family left empty was not created for the phase: absolute exchanges are optional in Clearing,
    loss variables only exist in ATC and, in Clearing, only for borders with losses.
    """

    exchange: dict[str, TemporalVariable]
    positive_exchange: dict[str, TemporalVariable] = field(default_factory=dict)
    negative_exchange: dict[str, TemporalVariable] = field(default_factory=dict)
    imports: dict[str, TemporalVariable] = field(default_factory=dict)
    exports: dict[str, TemporalVariable] = field(default_factory=dict)
    xsis: dict[str, TemporalVariable] = field(default_factory=dict)
    nus: dict[str, TemporalVariable] = field(default_factory=dict)


def add_border_variables(
    model: OptimisationModel,
    input_dataset: MarketClearingInputDataset,
    with_absolute_exchanges: bool,
    only_borders_with_losses: bool,
) -> BorderVariables:
    """Create the border variables of a phase model over the clearing times.

    In ATC, exchanges are bounded by the border flow limits; in flow-based they are free and
    the critical branches constrain them instead.

    :param model: Model of the phase
    :type model: OptimisationModel
    :param input_dataset: Market clearing input dataset
    :type input_dataset: MarketClearingInputDataset
    :param with_absolute_exchanges: Whether to create the positive and negative exchange variables
    :type with_absolute_exchanges: bool
    :param only_borders_with_losses: Whether to create the loss variables only for borders with a
        non-zero loss factor
    :type only_borders_with_losses: bool
    :return: The created border variables
    :rtype: BorderVariables
    """
    times = input_dataset.times
    borders = input_dataset.market_borders
    is_atc = input_dataset.is_atc

    variables = BorderVariables(
        exchange={
            name: model.add_temporal_variable(
                f"exchange_on_{name}",
                times,
                lower_bound=border.min_flow if is_atc else float("-inf"),
                upper_bound=border.max_flow if is_atc else float("inf"),
            )
            for name, border in borders.items()
        }
    )

    if with_absolute_exchanges:
        variables.positive_exchange = {
            name: model.add_temporal_variable(
                f"positive_exchange_on_{name}",
                times,
                lower_bound=0.0,
                upper_bound=border.max_flow if is_atc else DEFAULT_MAX_FLOW,
            )
            for name, border in borders.items()
        }
        variables.negative_exchange = {
            name: model.add_temporal_variable(
                f"negative_exchange_on_{name}",
                times,
                lower_bound=border.min_flow if is_atc else DEFAULT_MIN_FLOW,
                upper_bound=0.0,
            )
            for name, border in borders.items()
        }

    if is_atc:
        lossy_borders = [
            name
            for name, border in borders.items()
            if not only_borders_with_losses or (border.loss_factor and border.loss_factor != 0.0)
        ]
        variables.imports = {name: model.add_temporal_variable(f"import_on_{name}", times) for name in lossy_borders}
        variables.exports = {name: model.add_temporal_variable(f"export_on_{name}", times) for name in lossy_borders}
        variables.xsis = {name: model.add_temporal_variable(f"xsi_on_{name}", times) for name in lossy_borders}
        variables.nus = {name: model.add_temporal_variable(f"nu_on_{name}", times) for name in lossy_borders}

    return variables
