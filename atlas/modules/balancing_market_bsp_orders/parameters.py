"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingOrdersParameters.
"""

from pydantic import Field, field_validator

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import MarketType


class BSPBalancingOrdersParameters(AbstractModuleParameters):
    """Parameters for the BSP Balancing Orders Formulation module.

    :param product_type: Type of balancing market product to formulate orders for
    :type product_type: MarketType
    :param market_price_cap: Maximum price cap for balancing market orders, in euro/MWh
    :type market_price_cap: float
    :param with_combinatorial_options: Whether to formulate combinatorial (multi-timestep) orders
    :type with_combinatorial_options: bool
    :param market_area_names: List of market area names to include. Accepts 'All', 'None',
        or a semicolon-separated string like 'FR; BE; DE'
    :type market_area_names: list[str]
    :param excluded_equipments_: Raw list of equipment names to exclude. Use the
        'excluded_equipments' property for resolved access
    :type excluded_equipments_: list[str] | None
    :param excluded_technologies_: Raw list of technology class names to exclude. Use the
        'excluded_technologies' property for resolved access
    :type excluded_technologies_: list[str] | None
    :param hydro_storage_quantity_percentage: Percentage of available quantity offered for
        hydraulic and storage equipments, between 0 and 1
    :type hydro_storage_quantity_percentage: float
    :param with_fixed_id_markets: Whether intraday markets are fixed (affects storage constraint horizon)
    :type with_fixed_id_markets: bool
    :param conservative_stored_energy: Whether to apply a conservative stored energy constraint
        extending the storage adequacy horizon beyond the balancing time frame
    :type conservative_stored_energy: bool
    :param storage_price_threshold: Threshold ratio of maximum energy above which storage order
        prices are adjusted to limit excessive activations
    :type storage_price_threshold: float
    :param res_self_balancing: Whether renewable energy sources use a self-balancing strategy,
        enabling upward orders and specific downward self-balancing orders
    :type res_self_balancing: bool
    """

    product_type: MarketType = Field(
        description="Type of balancing market product to formulate orders for.",
    )
    market_price_cap: float = Field(
        description="Maximum price cap for balancing market orders, in euro/MWh.",
    )
    with_combinatorial_options: bool = Field(
        description="Whether to formulate combinatorial (multi-timestep linked) orders.",
    )

    market_area_names: str | list[str] = Field(
        description=(
            "List of market area names to include in order formulation. "
            "Accepts 'All' to include all available market areas, "
            "'None' for an empty selection, "
            "or a semicolon-separated string like 'FR; BE; DE'."
        ),
    )
    excluded_equipments_: list[str] | None = Field(
        None,
        description=(
            "List of equipment names to exclude from order formulation. 'None' and ['none'] resolve to an empty list."
        ),
        alias="excluded_equipments",
    )
    excluded_technologies_: list[str] | None = Field(
        None,
        description=(
            "List of technology class names to exclude from order formulation. "
            "'None' and ['none'] resolve to an empty list."
        ),
        alias="excluded_technologies",
    )

    hydro_storage_quantity_percentage: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Percentage of available quantity offered for hydraulic and storage equipments. Must be between 0 and 1."
        ),
    )
    with_fixed_id_markets: bool = Field(
        description=(
            "Whether intraday markets are considered fixed. "
            "Affects the storage adequacy constraint horizon computation."
        ),
    )
    conservative_stored_energy: bool = Field(
        description=(
            "Whether to apply a conservative stored energy constraint, "
            "extending the storage adequacy horizon beyond the balancing time frame."
        ),
    )
    storage_price_threshold: float = Field(
        ge=0.0,
        description=(
            "Threshold ratio of maximum energy above which storage order prices are adjusted "
            "to limit excessive activations on balancing markets."
        ),
    )

    res_self_balancing: bool = Field(
        description=(
            "Whether renewable energy sources use a self-balancing strategy. "
            "When True, enables upward orders and specific downward self-balancing orders for RES."
        ),
    )

    @property
    def excluded_equipments(self) -> list[str]:
        """List of equipment names excluded from order formulation."""
        val = self.excluded_equipments_
        if val is None:
            return []
        if len(val) == 1 and val[0].lower() == "none":
            return []
        if len(val) == 1 and val[0].lower() == "all":
            return ["all"]
        return val

    @property
    def excluded_technologies(self) -> list[str]:
        """List of technology class names excluded from order formulation."""
        val = self.excluded_technologies_
        if val is None:
            return []
        if len(val) == 1 and val[0].lower() == "none":
            return []
        if len(val) == 1 and val[0].lower() == "all":
            return ["all"]
        return val

    @field_validator("market_area_names", mode="before")
    @classmethod
    def parse_included_objects(cls, v):
        # case default
        if isinstance(v, str) and v.lower() == "all":
            return v.lower()

        # already a list
        if isinstance(v, list):
            return v

        # string like "[es, fr]"
        if isinstance(v, str):
            v = v.strip()

            if not (v.startswith("[") and v.endswith("]")):
                raise ValueError("market_area_names must be 'All' or a list like [es, fr]")

            content = v[1:-1].strip()
            if not content:
                return []

            return [item.strip() for item in content.split(",")]

        raise ValueError("Invalid value for market_area_names")
