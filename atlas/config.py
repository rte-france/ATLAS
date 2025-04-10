"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import Enum


class TimeSeriesInterpolation(Enum):
    """Defines interpolation types for Timeseries objects."""

    CONSTANT = "constant"
    LINEAR = "linear"
    LINEAR_AVERAGE = "linear_average"


class LoadType(str, Enum):
    BASE_LOAD = "BaseLoad"
    POWER_TO_GAS = "PowerToGas"
    OTHER_NON_DISPATCHABLE_LOAD = "OtherNonDispatchableLoad"


class StorageType(str, Enum):
    BATTERY = "Battery"
    PUMPED_HYDRAULIC_STORAGE = "PumpedHydraulicStorage"
    ELECTRIC_VEHICLE = "ElectricVehicle"


class ThermicStrategy(str, Enum):
    BASE = "Base"
    INTERMEDIATE = "Intermediate"
    PEAK = "Peak"


class ReservesTypes(str, Enum):
    FrBM = "FrBM"
    mFRR = "mFRR"  # noqa: N815
    aFRR = "aFRR"  # noqa: N815


class ComplementDirection(str, Enum):
    EqualTo = "EqualTo"
    GreaterThan = "GreaterThan"
    LesserThan = "LesserThan"


class CouplingType(str, Enum):
    EXCLUSION = "EXCLUSION"
    COMPLEMENT = "COMPLEMENT"
    IDENTICAL_VOLUME = "IDENTICAL_VOLUME"
    PARENT_CHILDREN = "PARENT_CHILDREN"
    IDENTICAL_RATIO = "IDENTICAL_RATIO"


class OrderType(str, Enum):
    Buy = "Buy"
    Sell = "Sell"


class Product(str, Enum):
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
