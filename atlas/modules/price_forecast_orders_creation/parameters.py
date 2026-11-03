from xmlrpc.client import DateTime

from pydantic import Field

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import Enum


class StoragePriceMethodType(str, Enum):
    """
    Represents different types of price determination method for storage orders.

    :cvar standard: FIXME - add description
    :cvar median: FIXME - add description
    :cvar buy_unbounded: FIXME - add description
    :cvar precompute: FIXME - add description
    """

    standard = "standard"
    median = "median"
    buy_unbounded = "buy_unbounded"
    precompute = "precompute"


class PriceForecastOrdersCreationParameters(AbstractModuleParameters):
    # Market parameters
    market: str = Field(
        "DayAhead",
        description="Type of market re-simulated. 'DayAhead' is advised, and should be passed to the Clearing as well",
    )
    market_price_cap: float = Field(
        3000,
        description="(Upper) price cap of the simulated market.",
    )
    epsilon: float = Field(
        0.001,
        description="Round off error permitted. If the difference between, two values is below Epsilon, they are considered identical.",
    )
    default_load_execution_date: DateTime = Field(
        default_factory=lambda: DateTime("30/06/2023 23:50:00"),
        description="FIXME MISSING DESCRIPTION.",
    )
    # Thermal parameters
    thermal_inelastic_price: float = Field(
        -500.0,
        description="Price (in euros/MWh) of thermal orders corresponding to inflexible / mustrun / inelastic generation.",
    )
    with_base_thermal_demand: float = Field(
        True,
        description="If True, a specific treatment is applied to thermal units with Base strategy. They will formulate demand instead of bids, to account for long term exchanges.",
    )
    with_opportunity_costs: float = Field(
        True,
        description="If True, additional opportunity costs are included in thermal unit prices, corresponding to costs occurring outside of the simulation time frame.",
    )
    # Storage parameters
    storage_price_method: StoragePriceMethodType = Field(
        StoragePriceMethodType.buy_unbounded,
        description="Type of price determination method for storage orders. Possible values: 'standard', 'median', 'buy_unbounded', 'precompute'",
    )
