"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal generation conversion models.
"""

from atlas.modules.antares_to_atlas.models.thermal.mixed_fuel import convert_mixed_fuel
from atlas.modules.antares_to_atlas.models.thermal.multi_energy import apply_multi_energy_costs
from atlas.modules.antares_to_atlas.models.thermal.nuclear_modulation import apply_nuclear_modulation
from atlas.modules.antares_to_atlas.models.thermal.particular_gas import convert_particular_mid_peak
from atlas.modules.antares_to_atlas.models.thermal.thermal import convert_thermal_units

__all__ = [
    "convert_thermal_units",
    "convert_mixed_fuel",
    "apply_multi_energy_costs",
    "apply_nuclear_modulation",
    "convert_particular_mid_peak",
]
