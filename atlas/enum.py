"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import Enum


class TimeSeriesInterpolation(Enum):
    """
    Defines interpolation types for Timeseries objects.

    :cvar CONSTANT: Constant value interpolation.
    :cvar LINEAR: Linear interpolation between points.
    :cvar LINEAR_AVERAGE: Linear interpolation with averaging logic.
    """

    CONSTANT = "constant"
    LINEAR = "linear"
    LINEAR_AVERAGE = "linear_average"


class LoadType(str, Enum):
    """
    Represents different types of electrical loads.

    :cvar BASE_LOAD: Base load consumption.
    :cvar POWER_TO_GAS: Power converted to gas.
    :cvar OTHER_NON_DISPATCHABLE_LOAD: Other loads that cannot be dispatched.
    """

    BASE_LOAD = "BaseLoad"
    POWER_TO_GAS = "PowerToGas"
    OTHER_NON_DISPATCHABLE_LOAD = "OtherNonDispatchableLoad"


class StorageType(str, Enum):
    """
    Represents different energy storage technologies.

    :cvar BATTERY: Battery storage.
    :cvar PUMPED_HYDRAULIC_STORAGE: Pumped hydroelectric storage.
    :cvar ELECTRIC_VEHICLE: Electric vehicle used as storage.
    """

    BATTERY = "Battery"
    PUMPED_HYDRAULIC_STORAGE = "PumpedHydraulicStorage"
    ELECTRIC_VEHICLE = "ElectricVehicle"


class ThermicStrategy(str, Enum):
    """
    Thermic generation strategy classification.

    :cvar BASE: Base-load thermal strategy.
    :cvar INTERMEDIATE: Intermediate thermal strategy.
    :cvar PEAK: Peak-load thermal strategy.
    """

    BASE = "Base"
    INTERMEDIATE = "Intermediate"
    PEAK = "Peak"


class ReservesTypes(str, Enum):
    """
    Types of reserves used in grid balancing.

    :cvar FrBM: Frequency Balancing Mechanism.
    :cvar mFRR: Manual Frequency Restoration Reserve.
    :cvar aFRR: Automatic Frequency Restoration Reserve.
    """

    FrBM = "FrBM"
    mFRR = "mFRR"  # noqa: N815
    aFRR = "aFRR"  # noqa: N815


class ComplementDirection(str, Enum):
    """
    Direction used in complementarity constraints.

    :cvar EqualTo: Equality constraint.
    :cvar GreaterThan: Greater-than constraint.
    :cvar LesserThan: Less-than constraint.
    """

    EqualTo = "EqualTo"
    GreaterThan = "GreaterThan"
    LesserThan = "LesserThan"


class CouplingType(str, Enum):
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


class OrderType(str, Enum):
    """
    Market order type.

    :cvar Buy: Purchase order.
    :cvar Sell: Sale order.
    """

    Buy = "Buy"
    Sell = "Sell"


class Product(str, Enum):
    """
    Enumeration of electricity market products.

    :cvar Intraday: Intraday market product.
    :cvar DayAhead: Day-ahead market product.
    :cvar AFRRUpProcurement: Upward aFRR reserve procurement.
    :cvar FRRDownProcurement: Downward FRR reserve procurement.
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
    FRRDownProcurement = "FRRDownProcurement"
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
