"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BSPBalancingOrdersParameters.
"""

from pydantic import Field, field_validator

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import MarketType


class BSPBalancingOrdersParameters(AbstractModuleParameters):
    """Parameters for the BSP Balancing Orders Formulation module.

    :param product_type: Type of balancing market product to formulate orders for.
        Accepted values: 'RRActivation', 'MFRRActivation'. Default: 'RRActivation'
    :type product_type: MarketType
    :param market_price_cap: Price cap of the market in euro/MWh, used as a symmetric cap
        and as the price of 'at all costs' bids. Usual values: 10000 for RR, 15000 for mFRR.
        Default: 15000
    :type market_price_cap: float
    :param with_combinatorial_options: Whether to formulate combinatorial (multi-timestep linked)
        orders. Default: True
    :type with_combinatorial_options: bool
    :param market_area_names: Market area names to include. Accepts 'all' to include all,
        or a list like '[FR, BE]'. Default: 'all'
    :type market_area_names: str | list[str]
    :param excluded_equipments_: Equipment names to exclude, semicolon-separated or as a list.
        'None' and ['none'] resolve to an empty list. Default: None
    :type excluded_equipments_: list[str] | None
    :param excluded_technologies_: Technology class names to exclude, semicolon-separated or
        as a list. 'None' and ['none'] resolve to an empty list. Default: None
    :type excluded_technologies_: list[str] | None
    :param hydro_storage_quantity_percentage: Fraction of available power offered for hydraulic
        and storage units. Should be kept at 1 unless used in specific studies. Default: 1.0
    :type hydro_storage_quantity_percentage: float
    :param with_fixed_id_markets: Whether the simulation includes fixed intraday markets.
        Affects the storage adequacy constraint horizon. Default: True
    :type with_fixed_id_markets: bool
    :param conservative_stored_energy: If True, storage units only provide reserves if reservoir
        constraints are respected until the next DA or ID market execution. Default: True
    :type conservative_stored_energy: bool
    :param storage_price_threshold: Fraction of MaximumEnergy above which activated balancing
        energy is considered excessive and order prices are adjusted. Default: 0.1
    :type storage_price_threshold: float
    :param res_self_balancing: Whether wind and solar units use the self-balancing strategy,
        enabling upward orders and specific downward self-balancing orders. Default: False
    :type res_self_balancing: bool
    """

    product_type: MarketType = Field(
        MarketType.rr_activation,
        description=(
            "Type of balancing market product to formulate orders for. "
            "Accepted values: 'RRActivation', 'MFRRActivation'."
        ),
    )
    market_price_cap: float = Field(
        15000,
        description=(
            "Price cap of the market in euro/MWh, used as a symmetric cap "
            "and as the price of 'at all costs' bids. "
            "Usual values: 10000 for RR markets, 15000 for mFRR markets."
        ),
    )
    with_combinatorial_options: bool = Field(
        True,
        description="Whether to formulate combinatorial (multi-timestep linked) orders.",
    )

    market_area_names: str | list[str] = Field(
        "all",
        description=(
            "Market area names to include in order formulation. "
            "Accepts 'All' to include all available market areas, "
            "or a list like '[FR, BE]'."
        ),
    )
    excluded_equipments_: list[str] | None = Field(
        None,
        description=(
            "Equipment names to exclude from order formulation. 'None' and ['none'] resolve to an empty list."
        ),
        alias="excluded_equipments",
    )
    excluded_technologies_: list[str] | None = Field(
        None,
        description=(
            "Technology class names to exclude from order formulation. 'None' and ['none'] resolve to an empty list."
        ),
        alias="excluded_technologies",
    )

    hydro_storage_quantity_percentage: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of available power offered for hydraulic and storage units. "
            "Should be kept at 1 unless used in specific studies."
        ),
    )
    with_fixed_id_markets: bool = Field(
        True,
        description=(
            "Whether the simulation includes fixed intraday markets. "
            "Affects the storage adequacy constraint horizon computation."
        ),
    )
    conservative_stored_energy: bool = Field(
        True,
        description=(
            "If True, storage units only provide reserves if reservoir constraints "
            "are respected until the next DA or ID market execution."
        ),
    )
    storage_price_threshold: float = Field(
        0.1,
        ge=0.0,
        description=(
            "Fraction of MaximumEnergy above which activated balancing energy is considered "
            "excessive and order prices are linearly adjusted."
        ),
    )

    res_self_balancing: bool = Field(
        False,
        description=(
            "Whether wind and solar units use the self-balancing strategy. "
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
