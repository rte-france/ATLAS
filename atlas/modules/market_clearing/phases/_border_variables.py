"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Border variables shared by the Clearing and ExchangesFixing phase models: both build the same
exchange variables, optionally split into positive and negative parts, and in ATC the same loss
variables (imports/exports/xsis/nus). The only behavioural difference between the two phases is
that Clearing only creates the loss variables for borders with a non-zero loss factor, while
ExchangesFixing creates them for every border.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from atlas.config import logger
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_border import DEFAULT_MAX_FLOW, DEFAULT_MIN_FLOW
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.temporal_variable import TemporalVariable

if TYPE_CHECKING:
    # ortools-stubs does not ship pywraplp (see the solver_interface mypy override)
    from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]


@dataclass(frozen=True)
class AbsoluteExchanges:
    """Positive and negative parts of the exchanges, keyed by border name."""

    positive: dict[str, TemporalVariable]
    negative: dict[str, TemporalVariable]

    def total(self) -> pywraplp.LinearExpr | int:
        """Sum of the absolute exchanges of every border over the clearing times, 0 without any border."""
        return sum(self.positive[name].sum() - self.negative[name].sum() for name in self.positive)


@dataclass(frozen=True)
class LossVariables:
    """Loss variables of one border: the flows before and after losses and their linearisation."""

    imports: TemporalVariable
    exports: TemporalVariable
    xsis: TemporalVariable
    nus: TemporalVariable


def add_exchange_variables(
    model: OptimisationModel, input_dataset: MarketClearingInputDataset
) -> dict[str, TemporalVariable]:
    """Create the exchange of each border over the clearing times.

    In ATC, exchanges are bounded by the border flow limits; in flow-based they are free and the
    critical branches constrain them instead.

    :param model: Model of the phase
    :type model: OptimisationModel
    :param input_dataset: Market clearing input dataset
    :type input_dataset: MarketClearingInputDataset
    :return: Exchange of each border, keyed by border name
    :rtype: dict[str, TemporalVariable]
    """
    is_atc = input_dataset.is_atc
    return {
        name: model.add_temporal_variable(
            f"exchange_on_{name}",
            input_dataset.times,
            lower_bound=border.min_flow if is_atc else float("-inf"),
            upper_bound=border.max_flow if is_atc else float("inf"),
        )
        for name, border in input_dataset.market_borders.items()
    }


def add_absolute_exchanges(model: OptimisationModel, input_dataset: MarketClearingInputDataset) -> AbsoluteExchanges:
    """Create the positive and negative parts of the exchange of each border over the clearing times.

    :param model: Model of the phase
    :type model: OptimisationModel
    :param input_dataset: Market clearing input dataset
    :type input_dataset: MarketClearingInputDataset
    :return: Positive and negative parts of the exchanges
    :rtype: AbsoluteExchanges
    """

    is_atc = input_dataset.is_atc
    borders = input_dataset.market_borders
    # In the current version, the optimization can crash in the rare corner case when
    # border.max_flow takes a nagative value and loss_factor is different from 0.
    # This will be corrected in later versions. For now, we raise an explicit error to
    # guide the user if this case happens
    if is_atc:
        for name, border in borders.items():
            if not border.loss_factor or border.loss_factor <= 0.0:
                continue

            if border.max_flow.min() < 0.0:
                logger.warning(
                    f"The exchange fixing problem may crash because of border {name}."
                    "maximum_flow takes negative values (which is fine), but also has a "
                    "non 0 loss factor. This combination is currently not supported"
                )

            if border.min_flow.max() > 0.0:
                logger.warning(
                    f"The exchange fixing problem may crash because of border {name}."
                    "minimum_flow takes positive values (which is fine), but also has a "
                    "non 0 loss factor. This combination is currently not supported"
                )

    return AbsoluteExchanges(
        positive={
            name: model.add_temporal_variable(
                f"positive_exchange_on_{name}",
                input_dataset.times,
                lower_bound=0.0,
                # In ATC, the positive part is bounded by ``max(max_flow, 0)``:
                # a border may have a negative maximum flow, in which case the unclipped bound
                # would conflict with the 0 bound of the part and make the model infeasible.
                upper_bound=border.max_flow.clip(lower_bound=0.0, inplace=False) if is_atc else DEFAULT_MAX_FLOW,
            )
            for name, border in borders.items()
        },
        negative={
            name: model.add_temporal_variable(
                f"negative_exchange_on_{name}",
                input_dataset.times,
                # Symmetrical bounding
                lower_bound=border.min_flow.clip(upper_bound=0.0, inplace=False) if is_atc else DEFAULT_MIN_FLOW,
                upper_bound=0.0,
            )
            for name, border in borders.items()
        },
    )


def add_loss_variables(
    model: OptimisationModel, input_dataset: MarketClearingInputDataset, only_borders_with_losses: bool
) -> dict[str, LossVariables]:
    """Create the loss variables of the borders over the clearing times. Losses are only modelled in ATC.

    :param model: Model of the phase
    :type model: OptimisationModel
    :param input_dataset: Market clearing input dataset
    :type input_dataset: MarketClearingInputDataset
    :param only_borders_with_losses: Whether to create them only for borders with a non-zero loss factor
    :type only_borders_with_losses: bool
    :return: Loss variables of each border that has them, keyed by border name; empty in flow-based
    :rtype: dict[str, LossVariables]
    """
    if not input_dataset.is_atc:
        return {}
    times = input_dataset.times
    return {
        name: LossVariables(
            imports=model.add_temporal_variable(f"import_on_{name}", times),
            exports=model.add_temporal_variable(f"export_on_{name}", times),
            xsis=model.add_temporal_variable(f"xsi_on_{name}", times),
            nus=model.add_temporal_variable(f"nu_on_{name}", times),
        )
        for name, border in input_dataset.market_borders.items()
        if not only_borders_with_losses or border.loss_factor
    }
