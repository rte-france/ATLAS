"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
    from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
    from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
    from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
    from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
    from atlas.modules.portfolio_optimisation.input_objects.thermal.thermal import ThermalPO
    from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO


def create_po_step(equipment):
    from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
    from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
    from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
    from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
    from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
    from atlas.modules.portfolio_optimisation.input_objects.thermal.thermal import ThermalPO
    from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
    from atlas.modules.portfolio_optimisation.steps.hydro import HydroPOStep
    from atlas.modules.portfolio_optimisation.steps.load import LoadPOStep
    from atlas.modules.portfolio_optimisation.steps.other_non_dispatchable import OtherNonDispatchablePOStep
    from atlas.modules.portfolio_optimisation.steps.solar import SolarPOStep
    from atlas.modules.portfolio_optimisation.steps.storage import StoragePOStep
    from atlas.modules.portfolio_optimisation.steps.thermal import ThermalPOStep
    from atlas.modules.portfolio_optimisation.steps.wind import WindPOStep

    if isinstance(equipment, ThermalPO):
        return ThermalPOStep(equipment)
    if isinstance(equipment, StoragePO):
        return StoragePOStep(equipment)
    if isinstance(equipment, HydroPO):
        return HydroPOStep(equipment)
    if isinstance(equipment, WindPO):
        return WindPOStep(equipment)
    if isinstance(equipment, SolarPO):
        return SolarPOStep(equipment)
    if isinstance(equipment, LoadPO):
        return LoadPOStep(equipment)
    if isinstance(equipment, OtherNonDispatchablePO):
        return OtherNonDispatchablePOStep(equipment)
    raise ValueError(f"No step class found for equipment type: {type(equipment)}")
