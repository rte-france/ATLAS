"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import Enum, StrEnum


class BusinessModelName(StrEnum):
    CONTROL_BLOCK = "control_block"
    CRITICAL_BRANCH = "critical_branch"
    EQUIPMENT = "equipment"
    HYDRO = "hydro"
    LOAD = "load"
    MARKET_AREA = "market_area"
    MARKET_AREA_PTDF = "market_area_ptdf"
    MARKET_BORDER = "market_border"
    NODE = "node"
    NODE_PTDF = "node_ptdf"
    ORDER = "order"
    ORDER_COUPLING = "order_coupling"
    OTHER_NON_DISPATCHABLE = "other_non_dispatchable"
    SOLAR = "solar"
    PORTFOLIO = "portfolio"
    STORAGE = "storage"
    THERMAL = "thermal"
    WIND = "wind"


class LoadType(StrEnum):
    """
    Represents different types of electrical loads.

    :cvar BASE_LOAD: Base load consumption.
    :cvar POWER_TO_GAS: Power converted to gas.
    :cvar OTHER_NON_DISPATCHABLE_LOAD: Other loads that cannot be dispatched.
    """

    BASE_LOAD = "BaseLoad"
    POWER_TO_GAS = "PowerToGas"
    OTHER_NON_DISPATCHABLE_LOAD = "OtherNonDispatchableLoad"


class StorageType(StrEnum):
    """
    Represents different energy storage technologies.

    :cvar BATTERY: Battery storage.
    :cvar PUMPED_HYDRAULIC_STORAGE: Pumped hydroelectric storage.
    :cvar ELECTRIC_VEHICLE: Electric vehicle used as storage.
    """

    BATTERY = "Battery"
    PUMPED_HYDRAULIC_STORAGE = "PumpedHydraulicStorage"
    ELECTRIC_VEHICLE = "ElectricVehicle"


class ThermalStrategy(StrEnum):
    """
    Thermal generation strategy classification.

    :cvar BASE: Base-load thermal strategy.
    :cvar INTERMEDIATE: Intermediate thermal strategy.
    :cvar PEAK: Peak-load thermal strategy.
    """

    BASE = "Base"
    INTERMEDIATE = "Intermediate"
    PEAK = "Peak"


class ReservesTypes(StrEnum):
    """
    Types of reserves used in grid balancing.

    :cvar FrBM: Frequency Balancing Mechanism.
    :cvar mFRR: Manual Frequency Restoration Reserve.
    :cvar aFRR: Automatic Frequency Restoration Reserve.
    """

    FrBM = "FrBM"
    mFRR = "mFRR"  # noqa: N815
    aFRR = "aFRR"  # noqa: N815


class ComplementDirection(StrEnum):
    """
    Direction used in complementarity constraints.

    :cvar EqualTo: Equality constraint.
    :cvar GreaterThan: Greater-than constraint.
    :cvar LesserThan: Less-than constraint.
    """

    EqualTo = "EqualTo"
    GreaterThan = "GreaterThan"
    LesserThan = "LesserThan"


class CouplingType(StrEnum):
    """
    Type of coupling constraints between energy assets.

    :cvar EXCLUSION: Assets cannot be active together.
    :cvar COMPLEMENT: Assets complement each other.
    :cvar IDENTICAL_VOLUME: Assets must have equal energy volumes.
    :cvar PARENT_CHILDREN: Hierarchical relationship.
    :cvar IDENTICAL_RATIO: Coupling via fixed ratio.
    """

    EXCLUSION = "EXCLUSION"
    COMPLEMENT = "COMPLEMENT"
    IDENTICAL_VOLUME = "IDENTICAL_VOLUME"
    PARENT_CHILDREN = "PARENT_CHILDREN"
    IDENTICAL_RATIO = "IDENTICAL_RATIO"
    ATC = "ATC"


class OrderType(StrEnum):
    """
    Market order type.

    :cvar Buy: Purchase order.
    :cvar Sell: Sale order.
    """

    Buy = "Buy"
    Sell = "Sell"


class Product(StrEnum):
    """
    Enumeration of electricity market products.

    :cvar Intraday: Intraday market product.
    :cvar DayAhead: Day-ahead market product.
    :cvar AFRRUpProcurement: Upward aFRR reserve procurement.
    :cvar AFRRDownProcurement: Downward aFRR reserve procurement.
    :cvar MFRRUpProcurement: Upward mFRR reserve procurement.
    :cvar MFRRDownProcurement: Downward mFRR reserve procurement.
    :cvar RRUpProcurement: Upward replacement reserve procurement.
    :cvar RRDownProcurement: Downward replacement reserve procurement.
    :cvar AFRRActivation: Activation of aFRR reserves.
    :cvar MFRRActivation: Activation of mFRR reserves.
    :cvar RRActivation: Activation of replacement reserves.
    :cvar FCRActivation: Activation of frequency containment reserves.
    :cvar FCRUpProcurement: Upward FCR reserve procurement.
    :cvar FCRDownProcurement: Downward FCR reserve procurement.
    """

    Intraday = "Intraday"
    DayAhead = "DayAhead"
    AFRRUpProcurement = "AFRRUpProcurement"
    AFRRDownProcurement = "AFRRDownProcurement"
    MFRRUpProcurement = "MFRRUpProcurement"
    MFRRDownProcurement = "MFRRDownProcurement"
    RRUpProcurement = "RRUpProcurement"
    RRDownProcurement = "RRDownProcurement"
    AFRRActivation = "AFRRActivation"
    MFRRActivation = "MFRRActivation"
    RRActivation = "RRActivation"
    FCRActivation = "FCRActivation"
    FCRUpProcurement = "FCRUpProcurement"
    FCRDownProcurement = "FCRDownProcurement"


class SolverStatus(Enum):
    """Enumeration of solver status codes."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    ABNORMAL = "abnormal"
    NOT_SOLVED = "not_solved"
    MODEL_INVALID = "model_invalid"


class InflowFrequency(StrEnum):
    """
    Frequency of inflow data.

    :cvar Daily: Daily frequency.
    :cvar Monthly: Monthly frequency.
    """

    Daily = "Daily"
    Monthly = "Monthly"


class MarketType(StrEnum):
    """
    Enumeration of market types.

    :cvar dayahead: Day-ahead market.
    :cvar intraday: Intraday market.
    :cvar rr_activation: Replacement reserve activation.
    :cvar mfrr_activation: Manual frequency restoration reserve activation.
    """

    dayahead = "DayAhead"
    intraday = "Intraday"
    rr_activation = "RRActivation"
    mfrr_activation = "MFRRActivation"


class SolverEnum(StrEnum):
    """
    Enumeration of solver types.

    :cvar XPRESS: Xpress solver.
    :cvar GLOP: Google Linear Optimization solver.
    :cvar SCIP: SCIP solver.
    :cvar CPSAT: Google CP-SAT solver.
    :cvar GUROBI: Gurobi solver.
    :cvar CBC: CBC solver.
    :cvar HIGHS: HiGHS solver.
    """

    XPRESS = "XPRESS"
    GLOP = "GLOP"
    SCIP = "SCIP"
    CPSAT = "CP-SAT"
    GUROBI = "GUROBI"
    CBC = "CBC"
    HIGHS = "HIGHS"


ENUM_TYPE_MAPPING = {
    "LoadType": LoadType,
    "StorageType": StorageType,
    "ThermalStrategy": ThermalStrategy,
    "ReservesTypes": ReservesTypes,
    "ComplementDirection": ComplementDirection,
    "CouplingType": CouplingType,
    "OrderType": OrderType,
    "Product": Product,
    "InflowFrequency": InflowFrequency,
}

INVERSE_ENUM_TYPE_MAPPING = {v: k for k, v in ENUM_TYPE_MAPPING.items()}
