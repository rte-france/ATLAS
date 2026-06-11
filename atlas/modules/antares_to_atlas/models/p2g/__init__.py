"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

P2G (Power-to-Gas) and associated thermal models conversion from Antares to Atlas.
"""

from atlas.modules.antares_to_atlas.models.p2g.multi_energy import update_variable_cost_for_gas_units
from atlas.modules.antares_to_atlas.models.p2g.p2g import convert_p2g_units
from atlas.modules.antares_to_atlas.models.p2g.particular_mid_peak import (
    convert_pcomp_mid_units,
    convert_pcomp_peak_units,
)

__all__ = [
    "convert_p2g_units",
    "update_variable_cost_for_gas_units",
    "convert_pcomp_mid_units",
    "convert_pcomp_peak_units",
]
